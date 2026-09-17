// misterzine image service: arcade screenshots by MAME setname, from R2.
//
// The MisterZine frontend on a MiSTer shows arcade games it finds on the card
// that the catalogue does not list. For those it asks this service for a
// picture by setname. The bucket is seeded once from the progettoSNAPS packs
// (tools/seed_r2.py), so nearly every request is a plain read; a miss may,
// when UPSTREAM_ENABLED is "1", fetch the picture once from Arcade Database
// or libretro-thumbnails and keep it, so no upstream ever sees a setname twice.
//
// Routes:
//   GET/HEAD /snap/<setname>.png    in-game screenshot
//   GET/HEAD /title/<setname>.png   title screen
//   GET      /healthz               {"ok":true, ...seed summary}
//   GET      /                      service info
//
// R2 layout:
//   snap/<sn>.png, title/<sn>.png   PNG; customMetadata {w, h, src, seeded_at}
//   neg/<kind>/<sn>                 remembered miss; customMetadata {until, tries, last_reason}
//   lock/<kind>/<sn>                one upstream fetch at a time; customMetadata {exp}
//   meta/parent.json                {setname: parent}  (clone -> parent fallback)
//   meta/desc.json                  {setname: MAME description} (libretro file names)
//   meta/seed.json                  what the seeder uploaded, for /healthz
//   meta/upstream/<YYYYMMDDHH>      hourly upstream fetch counter
//
// Nothing about the requester is stored or logged; only upstream outcomes are.

const SETNAME_RE = /^[a-z0-9_]{1,32}$/;
const KINDS = { snap: 'ingames', title: 'titles' }; // our kind -> Arcade Database folder
const LIBRETRO_FOLDER = { snap: 'Named_Snaps', title: 'Named_Titles' };
const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const BLANK_CHECK_MAX = 512 * 1024;
const UPSTREAM_BUDGET_MS = 5000;
const ADB_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
  Referer: 'https://adb.arcadeitalia.net/',
};

let parentMap = null; // loaded from R2 on the first miss in this isolate
let descMap = null;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders() });
    let res;
    try {
      res = await route(request, env, ctx, url);
    } catch (e) {
      console.error('unhandled', e && e.stack || e);
      res = json({ error: 'internal' }, 500);
    }
    return res;
  },
};

async function route(request, env, ctx, url) {
  const m = request.method, p = url.pathname.replace(/\/+$/, '') || '/';
  let mm;
  if ((mm = p.match(/^\/(snap|title)\/([^/]+)\.png$/))) {
    if (m !== 'GET' && m !== 'HEAD') return json({ error: 'method' }, 405);
    return serveImage(mm[1], mm[2], request, env, ctx, url);
  }
  if (m !== 'GET') return json({ error: 'method' }, 405);
  if (p === '/') return json({ name: 'misterzine image service', docs: 'https://github.com/matijaerceg/misterzine/tree/main/images' });
  if (p === '/healthz') {
    const seed = await readJSONObject(env, 'meta/seed.json');
    return json({ ok: true, upstream: env.UPSTREAM_ENABLED === '1', seed: seed || null });
  }
  return json({ error: 'not_found' }, 404);
}

// --- images ---------------------------------------------------------------------

async function serveImage(kind, sn, request, env, ctx, url) {
  if (!SETNAME_RE.test(sn)) return miss('invalid', 86400);
  // The edge cache sits in front of R2 in production; EDGE_CACHE "0" (tests)
  // goes straight to the bucket.
  const cache = env.EDGE_CACHE === '0' ? null : caches.default;
  const cacheKey = new Request(url.origin + url.pathname, { method: 'GET' });
  const cached = cache && await cache.match(cacheKey);
  if (cached) return finish(cached, request);

  const key = `${kind}/${sn}.png`;
  let obj = await env.IMAGES.get(key);
  let source = obj && obj.customMetadata && obj.customMetadata.src || 'seed';
  if (!obj) {
    const found = await onMiss(kind, sn, env);
    if (found.response) {
      if (found.cacheable && cache) ctx.waitUntil(cache.put(cacheKey, found.response.clone()));
      return finish(found.response, request);
    }
    obj = found.object;
    source = found.source;
  }
  // Buffer the picture: screenshots are small, and a buffered body clones
  // freely into the edge cache while the original streams to the client.
  const res = hit(obj, source, await obj.arrayBuffer());
  if (cache) ctx.waitUntil(cache.put(cacheKey, res.clone()));
  return finish(res, request);
}

// onMiss resolves a key R2 lacks: a remembered miss, the parent's picture, or
// one upstream fetch. Returns {object, source} for a picture now in R2, or
// {response, cacheable} for a 404.
async function onMiss(kind, sn, env) {
  const neg = await env.IMAGES.head(`neg/${kind}/${sn}`);
  if (neg && neg.customMetadata && Date.parse(neg.customMetadata.until) > Date.now()) {
    return { response: miss('negative', 86400), cacheable: true };
  }
  const parent = (await parents(env))[sn];
  if (parent && parent !== sn) {
    const pobj = await env.IMAGES.get(`${kind}/${parent}.png`);
    if (pobj) {
      const buf = await pobj.arrayBuffer();
      const meta = { ...(pobj.customMetadata || {}), src: `parent:${parent}` };
      await env.IMAGES.put(`${kind}/${sn}.png`, buf, { httpMetadata: { contentType: 'image/png' }, customMetadata: meta });
      const obj = await env.IMAGES.get(`${kind}/${sn}.png`);
      if (obj) return { object: obj, source: meta.src };
    }
  }
  if (env.UPSTREAM_ENABLED !== '1') return { response: miss('negative', 86400), cacheable: true };
  if (!(await takeUpstreamToken(env))) return { response: miss('capped', 3600, 3600), cacheable: false };
  if (!(await takeLock(kind, sn, env))) return { response: miss('inflight', 0, 30), cacheable: false };
  try {
    const got = await fetchUpstream(kind, sn, env);
    if (got) {
      await env.IMAGES.put(`${kind}/${sn}.png`, got.bytes, {
        httpMetadata: { contentType: 'image/png' },
        customMetadata: { w: String(got.w), h: String(got.h), src: got.src, seeded_at: new Date().toISOString() },
      });
      console.log(`upstream hit ${kind}/${sn} from ${got.src}`);
      const obj = await env.IMAGES.get(`${kind}/${sn}.png`);
      return { object: obj, source: got.src };
    }
    await rememberMiss(kind, sn, env, neg, 'upstream_miss');
    console.log(`upstream miss ${kind}/${sn}`);
    return { response: miss('negative', 86400), cacheable: true };
  } finally {
    await env.IMAGES.delete(`lock/${kind}/${sn}`);
  }
}

async function fetchUpstream(kind, sn, env) {
  const deadline = Date.now() + UPSTREAM_BUDGET_MS;
  const adb = `https://adb.arcadeitalia.net/media/mame.current/${KINDS[kind]}/${sn}.png`;
  let got = await fetchPNG(adb, ADB_HEADERS, deadline);
  if (got) return { ...got, src: 'adb' };
  const desc = (await descs(env))[sn];
  if (desc && Date.now() < deadline) {
    const name = libretroName(desc);
    const url = `https://raw.githubusercontent.com/libretro-thumbnails/MAME/master/${LIBRETRO_FOLDER[kind]}/${encodeURIComponent(name)}.png`;
    got = await fetchPNG(url, {}, deadline);
    if (got) return { ...got, src: 'libretro' };
  }
  return null;
}

// fetchPNG returns {bytes, w, h} for a real, non-blank PNG, else null.
async function fetchPNG(url, headers, deadline) {
  const ms = deadline - Date.now();
  if (ms <= 0) return null;
  let res;
  try {
    res = await fetch(url, { headers, signal: AbortSignal.timeout(ms), cf: { cacheTtl: 0 } });
  } catch (e) {
    return null;
  }
  if (!res.ok) return null;
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (!isPNG(bytes)) return null;
  const dims = pngDims(bytes);
  if (!dims) return null;
  if (bytes.length <= BLANK_CHECK_MAX && await pngIsBlank(bytes)) return null;
  return { bytes, w: dims.w, h: dims.h };
}

// libretro-thumbnails names files after the MAME description with the
// characters &*/:`<>?\| replaced by an underscore.
export function libretroName(desc) {
  return desc.replace(/[&*/:`<>?\\|]/g, '_');
}

export function isPNG(bytes) {
  if (bytes.length < 24) return false;
  for (let i = 0; i < PNG_MAGIC.length; i++) if (bytes[i] !== PNG_MAGIC[i]) return false;
  return true;
}

export function pngDims(bytes) {
  if (!isPNG(bytes)) return null;
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const w = dv.getUint32(16), h = dv.getUint32(20);
  return w > 0 && h > 0 ? { w, h } : null;
}

// pngIsBlank inflates the IDAT stream and reports an all-zero image (the
// black frames upstream keeps for laserdisc games). Any trouble means "not
// blank": never reject a real capture.
export async function pngIsBlank(bytes) {
  try {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const parts = [];
    let pos = 8, total = 0;
    while (pos + 8 <= bytes.length) {
      const n = dv.getUint32(pos);
      const type = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);
      if (type === 'IDAT') { parts.push(bytes.subarray(pos + 8, pos + 8 + n)); total += n; }
      else if (type === 'IEND') break;
      pos += 12 + n;
    }
    if (!total) return false;
    const raw = new Uint8Array(total);
    let off = 0;
    for (const p of parts) { raw.set(p, off); off += p.length; }
    const stream = new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate'));
    const reader = stream.getReader();
    let any = false;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      any = true;
      for (let i = 0; i < value.length; i++) if (value[i] !== 0) return false;
    }
    return any;
  } catch (e) {
    return false;
  }
}

// --- bookkeeping ------------------------------------------------------------------

async function parents(env) {
  if (!parentMap) parentMap = (await readJSONObject(env, 'meta/parent.json')) || {};
  return parentMap;
}
async function descs(env) {
  if (!descMap) descMap = (await readJSONObject(env, 'meta/desc.json')) || {};
  return descMap;
}
async function readJSONObject(env, key) {
  const obj = await env.IMAGES.get(key);
  if (!obj) return null;
  try { return await obj.json(); } catch (e) { return null; }
}

// takeUpstreamToken counts upstream fetches per hour in one small object.
// Read-then-write is approximate under concurrency; the cap is a ceiling on
// abuse, not an accounting.
async function takeUpstreamToken(env) {
  const cap = parseInt(env.UPSTREAM_HOURLY_CAP || '60', 10);
  const key = 'meta/upstream/' + new Date().toISOString().slice(0, 13).replace(/[-T]/g, '');
  const obj = await env.IMAGES.get(key);
  const n = obj ? parseInt(await obj.text(), 10) || 0 : 0;
  if (n >= cap) return false;
  await env.IMAGES.put(key, String(n + 1));
  return true;
}

// takeLock marks one fetch in flight for LOCK_SECONDS. R2 has no
// compare-and-swap, so two requests in the same instant may both proceed; the
// cost is one duplicate upstream fetch for one setname.
async function takeLock(kind, sn, env) {
  const key = `lock/${kind}/${sn}`;
  const cur = await env.IMAGES.head(key);
  if (cur && cur.customMetadata && Number(cur.customMetadata.exp) > Date.now()) return false;
  const seconds = parseInt(env.LOCK_SECONDS || '30', 10);
  await env.IMAGES.put(key, '', { customMetadata: { exp: String(Date.now() + seconds * 1000) } });
  return true;
}

async function rememberMiss(kind, sn, env, prev, reason) {
  const tries = (prev && prev.customMetadata && parseInt(prev.customMetadata.tries, 10) || 0) + 1;
  const maxTries = parseInt(env.NEG_MAX_TRIES || '3', 10);
  const days = tries >= maxTries ? 3650 : parseInt(env.NEG_TTL_DAYS || '30', 10);
  const until = new Date(Date.now() + days * 86400 * 1000).toISOString();
  await env.IMAGES.put(`neg/${kind}/${sn}`, '', { customMetadata: { until, tries: String(tries), last_reason: reason } });
}

// --- responses ----------------------------------------------------------------------

function hit(obj, source, body) {
  const meta = obj.customMetadata || {};
  const headers = {
    'Content-Type': 'image/png',
    'Content-Length': String(body.byteLength),
    'Cache-Control': 'public, max-age=31536000, immutable',
    ETag: obj.httpEtag,
    'X-Image-Source': source,
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Expose-Headers': 'ETag, X-Image-Width, X-Image-Height, X-Image-Source',
  };
  if (meta.w && meta.h) { headers['X-Image-Width'] = meta.w; headers['X-Image-Height'] = meta.h; }
  return new Response(body, { status: 200, headers });
}

// miss is a 404 the device treats like any other missing picture. maxAge
// lets the edge absorb repeats; retry tells a polite client when to ask again.
function miss(why, maxAge, retry) {
  const headers = {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': maxAge > 0 ? `public, max-age=${maxAge}` : 'no-store',
    'Retry-After': String(retry || maxAge || 30),
    'X-Image-Miss': why,
    'Access-Control-Allow-Origin': '*',
  };
  return new Response('not found\n', { status: 404, headers });
}

// finish applies conditional and HEAD semantics to a built response.
function finish(res, request) {
  const etag = res.headers.get('ETag');
  if (etag && request.headers.get('If-None-Match') === etag) {
    return new Response(null, { status: 304, headers: { ETag: etag, 'Cache-Control': res.headers.get('Cache-Control') || '' } });
  }
  if (request.method === 'HEAD') return new Response(null, { status: res.status, headers: res.headers });
  return res;
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Access-Control-Allow-Headers': 'If-None-Match',
    'Access-Control-Max-Age': '86400',
  };
}
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*' },
  });
}
