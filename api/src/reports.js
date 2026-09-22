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
// New codes use only characters nothing else can be mistaken for in the
// MiSTer's font or a forum post: no 0/O/Q/D, 1/I/L, 2/Z, 5/S, 8/B, 6/G, U/V.
// Twenty of them make 20^4 = 160,000 four-character codes, plenty for thirty
// days of reports: a code is an identifier, not a key (reading needs the
// admin token). A code can come back after its report expires, so a reader
// checks the upload date.
export const ALPHABET = '34679ACEFHJKMNPRTWXY';
const CODE_LEN = 4;
// Reading accepts any Crockford base32 code, so reports filed before the
// alphabet narrowed (their codes may hold 0, 1, B, ...) stay readable.
const CODE_RE = new RegExp('^[0-9A-HJKMNP-TV-Z]{' + CODE_LEN + '}$');
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
  // A code is claimed by a put that succeeds only while no object has the
  // key, so two uploads at once can never share one: a taken code (live, or
  // expired and not yet swept) just means another draw.
  const opts = {
    httpMetadata: { contentType: 'text/plain; charset=utf-8' },
    customMetadata: { app: appLine(text) },
    onlyIf: new Headers({ 'If-None-Match': '*' }),
  };
  for (let i = 0; i < 10; i++) {
    const code = newCode();
    if (await env.REPORTS.put(key(code), bytes, opts)) return json({ code }, 201);
  }
  return json({ error: 'internal' }, 500);
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

// newCode draws CODE_LEN characters uniformly from ALPHABET: a random byte
// counts only below the largest multiple of the alphabet's size.
function newCode() {
  const limit = 256 - (256 % ALPHABET.length);
  let code = '';
  while (code.length < CODE_LEN) {
    const b = new Uint8Array(CODE_LEN * 2);
    crypto.getRandomValues(b);
    for (const x of b) {
      if (x < limit && code.length < CODE_LEN) code += ALPHABET[x % ALPHABET.length];
    }
  }
  return code;
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
