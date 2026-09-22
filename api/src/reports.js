// Device reports: the MisterZine Frontend's Troubleshooting -> Send a report
// uploads a plain-text diagnostic of the player's card, and the developer
// reads it by the short code the device shows. Nothing is stored about the
// sender: no account, no IP address (the rate limiter keys on the address in
// memory only), no device identifier beyond what the report text itself says.
//
// Reports live in their own private R2 bucket (binding REPORTS), never the
// public image bucket. A lifecycle rule on that bucket deletes each report 30
// days after upload; the read routes refuse anything older too, since the
// rule runs about once a day.
//
//   POST   /reports          device upload: text/plain starting with MAGIC,
//                            at most REPORT_MAX_BYTES; 201 {code}
//   GET    /reports          admin: {reports: [{code, uploaded, size, app}]}
//   GET    /reports/{code}   admin: the report, text/plain
//   DELETE /reports/{code}   admin: remove one early
//
// Admin routes take `Authorization: Bearer <REPORTS_TOKEN>` (a Worker
// secret), separate from account sessions. REPORTS_ENABLED other than "1"
// turns uploads off (503) without touching the app.

export const REPORT_DAYS = 30;
export const MAGIC = 'MisterZine report v1';
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'; // Crockford base32: no I, L, O, U
const CODE_RE = /^[0-9A-HJKMNP-TV-Z]{8}$/;
const DAY_MS = 86400000;

// reports answers every /reports route; now is injectable for tests.
export async function reports(request, env, m, p, now = Date.now()) {
  if (p === '/reports' && m === 'POST') return upload(request, env);
  const admin = await isAdmin(request, env);
  if (p === '/reports' && m === 'GET') {
    if (!admin) return json({ error: 'unauthorized' }, 401);
    return json({ reports: await listReports(env, now) });
  }
  const mm = p.match(/^\/reports\/([^/]+)$/);
  if (mm && (m === 'GET' || m === 'DELETE')) {
    if (!admin) return json({ error: 'unauthorized' }, 401);
    const code = normalizeCode(decodeURIComponent(mm[1]));
    if (!code) return json({ error: 'bad_code' }, 400);
    if (m === 'DELETE') {
      await env.REPORTS.delete(key(code));
      return new Response(null, { status: 204 });
    }
    const obj = await env.REPORTS.get(key(code));
    if (obj && expired(obj.uploaded, now)) await obj.body.cancel(); // the lifecycle rule has yet to run
    if (!obj || expired(obj.uploaded, now)) return json({ error: 'not_found' }, 404);
    return new Response(obj.body, {
      headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-Report-Uploaded': obj.uploaded.toISOString() },
    });
  }
  return json({ error: 'not_found' }, 404);
}

async function upload(request, env) {
  if (env.REPORTS_ENABLED !== '1') return json({ error: 'disabled' }, 503);
  if (env.REPORT_LIMIT) {
    const { success } = await env.REPORT_LIMIT.limit({ key: request.headers.get('CF-Connecting-IP') || 'unknown' });
    if (!success) return json({ error: 'rate_limited' }, 429);
  }
  const max = parseInt(env.REPORT_MAX_BYTES, 10) || 524288;
  if ((parseInt(request.headers.get('Content-Length'), 10) || 0) > max) return json({ error: 'too_large' }, 413);
  const bytes = await readCapped(request, max);
  if (!bytes) return json({ error: 'too_large' }, 413);
  const text = new TextDecoder().decode(bytes);
  if (!text.startsWith(MAGIC)) return json({ error: 'not_a_report' }, 400);
  let code = '';
  for (let i = 0; i < 5 && !code; i++) {
    const c = newCode();
    if (!(await env.REPORTS.head(key(c)))) code = c;
  }
  if (!code) return json({ error: 'internal' }, 500);
  await env.REPORTS.put(key(code), bytes, {
    httpMetadata: { contentType: 'text/plain; charset=utf-8' },
    customMetadata: { app: appLine(text) },
  });
  return json({ code }, 201);
}

async function listReports(env, now) {
  const out = [];
  let cursor;
  do {
    const page = await env.REPORTS.list({ prefix: 'r/', cursor, include: ['customMetadata'] });
    for (const o of page.objects) {
      if (expired(o.uploaded, now)) continue;
      out.push({ code: o.key.slice(2, -4), uploaded: o.uploaded.toISOString(), size: o.size, app: (o.customMetadata || {}).app || '' });
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor && out.length < 5000);
  return out.sort((a, b) => (a.uploaded < b.uploaded ? 1 : -1));
}

// readCapped reads the body, or returns null once it passes max bytes.
async function readCapped(request, max) {
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.byteLength;
    if (n > max) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(n);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.byteLength;
  }
  return out;
}

// appLine is the report's "App:" header line, for the admin list.
function appLine(text) {
  for (const line of text.split('\n', 12)) {
    if (line.startsWith('App: ')) return line.slice(5, 105).trim();
  }
  return '';
}

function newCode() {
  const b = new Uint8Array(8);
  crypto.getRandomValues(b);
  return [...b].map(x => ALPHABET[x & 31]).join('');
}

// normalizeCode accepts what a person types: any case, dashes and spaces,
// and the letters Crockford base32 reads as digits.
export function normalizeCode(s) {
  const c = s.toUpperCase().replace(/[\s-]/g, '').replace(/[IL]/g, '1').replace(/O/g, '0');
  return CODE_RE.test(c) ? c : '';
}

const key = code => 'r/' + code + '.txt';
const expired = (uploaded, now) => now - uploaded.getTime() > REPORT_DAYS * DAY_MS;

async function isAdmin(request, env) {
  const want = env.REPORTS_TOKEN;
  const bearer = /^Bearer\s+(\S+)\s*$/i.exec(request.headers.get('Authorization') || '');
  const got = bearer ? bearer[1] : '';
  if (!want || !got) return false;
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([crypto.subtle.digest('SHA-256', enc.encode(want)), crypto.subtle.digest('SHA-256', enc.encode(got))]);
  return crypto.subtle.timingSafeEqual(a, b);
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
