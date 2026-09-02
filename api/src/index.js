// misterzine account service: a Cloudflare Worker in front of a D1 database.
//
// What it does: signs people in with Google or GitHub (OAuth, no passwords),
// and stores their release-tracker favorites. That is the whole job. It holds
// no device addresses, no Zaparoo keys, no names, no avatars.
//
// Routes (all JSON unless noted; CORS is limited to SITE_ORIGIN + DEV_ORIGINS):
//   GET    /                          service info
//   GET    /auth/google?r=/releases/  start sign-in (browser navigation)
//   GET    /auth/github?r=/releases/  start sign-in (browser navigation)
//   GET    /auth/{provider}/callback  provider returns here; we redirect to
//                                     SITE_ORIGIN/auth/#t=<token>&new=1|0&r=<path>
//   GET    /me                        {provider, created_at, favorites}
//   DELETE /me                        delete the account (header X-Confirm: delete)
//   POST   /logout                    revoke this session
//   GET    /favorites                 {keys: [...]}
//   PUT    /favorites/{key}           add one
//   DELETE /favorites/{key}           remove one
//   POST   /favorites/import          {keys: [...]} union into the account (first sign-in)
//
// Auth for the JSON routes: `Authorization: Bearer <session token>`. The
// token is 32 random bytes (base64url); only its sha256 is stored. Sessions
// expire 90 days after last use. The OAuth start/callback pair is tied
// together by a signed, short-lived cookie (state + PKCE verifier + return
// path), so no server-side state is needed for sign-in.

const KEY_RE = /^[A-Za-z0-9_-]{1,64}$/;      // release tracker row keys (data.json `k`)
const MAX_FAVORITES = 5000;
const SESSION_DAYS = 90;
const COOKIE = 'mz_oauth';
const enc = new TextEncoder();

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(env, request.headers.get('Origin'));
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    let res;
    try {
      res = await route(request, env, url);
    } catch (e) {
      console.error('unhandled', e && e.stack || e);
      res = json({ error: 'internal' }, 500);
    }
    for (const [k, v] of Object.entries(cors)) res.headers.set(k, v);
    return res;
  },
};

async function route(request, env, url) {
  const m = request.method, p = url.pathname.replace(/\/+$/, '') || '/';

  if (p === '/' && m === 'GET')
    return json({ name: 'misterzine account service', docs: 'https://github.com/matijaerceg/misterzine/tree/main/api' });

  // --- sign-in (browser navigations, not fetches) ---------------------------
  let mm;
  if (m === 'GET' && (mm = p.match(/^\/auth\/(google|github)$/))) return startOAuth(mm[1], env, url);
  if (m === 'GET' && (mm = p.match(/^\/auth\/(google|github)\/callback$/))) return finishOAuth(mm[1], env, url, request);

  // --- everything below needs a session -------------------------------------
  const user = await authenticate(request, env);
  if (!user) return json({ error: 'unauthorized' }, 401);

  if (p === '/me' && m === 'GET') {
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM favorites WHERE user_id = ?').bind(user.id).first('n');
    return json({ provider: user.provider, created_at: user.created_at, favorites: n });
  }
  if (p === '/me' && m === 'DELETE') {
    if (request.headers.get('X-Confirm') !== 'delete') return json({ error: 'confirm_required' }, 400);
    // ON DELETE CASCADE covers favorites + sessions, but delete explicitly too
    // so the result never depends on the foreign_keys pragma being on
    await env.DB.batch([
      env.DB.prepare('DELETE FROM favorites WHERE user_id = ?').bind(user.id),
      env.DB.prepare('DELETE FROM sessions WHERE user_id = ?').bind(user.id),
      env.DB.prepare('DELETE FROM users WHERE id = ?').bind(user.id),
    ]);
    return new Response(null, { status: 204 });
  }
  if (p === '/logout' && m === 'POST') {
    await env.DB.prepare('DELETE FROM sessions WHERE token_hash = ?').bind(user.token_hash).run();
    return new Response(null, { status: 204 });
  }
  if (p === '/favorites' && m === 'GET') {
    const { results } = await env.DB.prepare('SELECT key FROM favorites WHERE user_id = ? ORDER BY added_at, key')
      .bind(user.id).all();
    return json({ keys: results.map(r => r.key) });
  }
  if (p === '/favorites/import' && m === 'POST') {
    const body = await readJSON(request);
    const keys = body && Array.isArray(body.keys) ? [...new Set(body.keys)] : null;
    if (!keys || keys.length > MAX_FAVORITES || !keys.every(k => typeof k === 'string' && KEY_RE.test(k)))
      return json({ error: 'bad_keys' }, 400);
    const have = await env.DB.prepare('SELECT COUNT(*) AS n FROM favorites WHERE user_id = ?').bind(user.id).first('n');
    if (have + keys.length > MAX_FAVORITES) return json({ error: 'limit' }, 409);
    if (keys.length) {
      const stmt = env.DB.prepare('INSERT OR IGNORE INTO favorites (user_id, key) VALUES (?, ?)');
      // D1 batches are transactional; chunk to stay well under statement limits
      for (let i = 0; i < keys.length; i += 100)
        await env.DB.batch(keys.slice(i, i + 100).map(k => stmt.bind(user.id, k)));
    }
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM favorites WHERE user_id = ?').bind(user.id).first('n');
    return json({ favorites: n });
  }
  if ((mm = p.match(/^\/favorites\/([^/]+)$/)) && (m === 'PUT' || m === 'DELETE')) {
    const key = decodeURIComponent(mm[1]);
    if (!KEY_RE.test(key)) return json({ error: 'bad_key' }, 400);
    if (m === 'PUT') {
      const have = await env.DB.prepare('SELECT COUNT(*) AS n FROM favorites WHERE user_id = ?').bind(user.id).first('n');
      if (have >= MAX_FAVORITES) return json({ error: 'limit' }, 409);
      await env.DB.prepare('INSERT OR IGNORE INTO favorites (user_id, key) VALUES (?, ?)').bind(user.id, key).run();
    } else {
      await env.DB.prepare('DELETE FROM favorites WHERE user_id = ? AND key = ?').bind(user.id, key).run();
    }
    return new Response(null, { status: 204 });
  }
  return json({ error: 'not_found' }, 404);
}

// --- sessions -----------------------------------------------------------------

async function authenticate(request, env) {
  const h = request.headers.get('Authorization') || '';
  const token = h.startsWith('Bearer ') ? h.slice(7).trim() : '';
  if (!/^[A-Za-z0-9_-]{40,}$/.test(token)) return null;
  const hash = await sha256hex(token);
  const row = await env.DB.prepare(
    'SELECT s.token_hash, s.last_seen_at, u.id, u.provider, u.created_at FROM sessions s ' +
    'JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?').bind(hash).first();
  if (!row) return null;
  const last = Date.parse(row.last_seen_at), now = Date.now();
  if (now - last > SESSION_DAYS * 864e5) {
    await env.DB.prepare('DELETE FROM sessions WHERE token_hash = ?').bind(hash).run();
    return null;
  }
  // touch at most once a day; sliding expiry without a write per request
  if (now - last > 864e5)
    await env.DB.prepare("UPDATE sessions SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE token_hash = ?")
      .bind(hash).run();
  return row;
}

async function createSession(env, userId) {
  const token = b64url(crypto.getRandomValues(new Uint8Array(32)));
  await env.DB.prepare('INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)')
    .bind(await sha256hex(token), userId).run();
  return token;
}

// --- OAuth --------------------------------------------------------------------

const PROVIDERS = {
  google: {
    authorize: 'https://accounts.google.com/o/oauth2/v2/auth',
    token: 'https://oauth2.googleapis.com/token',
    scope: 'openid email',
    pkce: true,
  },
  github: {
    authorize: 'https://github.com/login/oauth/authorize',
    token: 'https://github.com/login/oauth/access_token',
    scope: '',                       // default: public profile only; email if public
    pkce: false,
  },
};

function creds(provider, env) {
  const id = env[provider.toUpperCase() + '_CLIENT_ID'], secret = env[provider.toUpperCase() + '_CLIENT_SECRET'];
  if (!id || !secret) throw new Error(provider + ' client not configured');
  return { id, secret };
}

async function startOAuth(provider, env, url) {
  const P = PROVIDERS[provider], { id } = creds(provider, env);
  // return path on the site after sign-in: a site-relative path only
  let r = url.searchParams.get('r') || '/releases/';
  if (!/^\/[A-Za-z0-9_\-./?=&%#]*$/.test(r) || r.startsWith('//')) r = '/releases/';
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));
  const verifier = P.pkce ? b64url(crypto.getRandomValues(new Uint8Array(32))) : '';
  const cookie = await signCookie(env, { s: state, v: verifier, r, p: provider, t: Date.now() });

  const q = new URLSearchParams({
    client_id: id, redirect_uri: apiOrigin(env, url) + '/auth/' + provider + '/callback',
    response_type: 'code', state,
  });
  if (P.scope) q.set('scope', P.scope);
  if (P.pkce) {
    q.set('code_challenge', b64url(await sha256bytes(verifier)));
    q.set('code_challenge_method', 'S256');
    q.set('prompt', 'select_account');
  }
  return new Response(null, {
    status: 302,
    headers: {
      Location: P.authorize + '?' + q,
      'Set-Cookie': COOKIE + '=' + cookie + '; Path=/auth; Max-Age=600; HttpOnly; Secure; SameSite=Lax',
      'Cache-Control': 'no-store',
    },
  });
}

async function finishOAuth(provider, env, url, request) {
  const P = PROVIDERS[provider];
  const fail = code => new Response(null, {
    status: 302,
    headers: { Location: env.SITE_ORIGIN + '/auth/#error=' + code, 'Set-Cookie': clearCookie(), 'Cache-Control': 'no-store' },
  });
  const cookie = parseCookies(request.headers.get('Cookie') || '')[COOKIE];
  const st = cookie ? await verifyCookie(env, cookie) : null;
  if (!st || st.p !== provider || Date.now() - st.t > 600e3) return fail('state');
  if (url.searchParams.get('error')) return fail('denied');
  const code = url.searchParams.get('code');
  if (!code || url.searchParams.get('state') !== st.s) return fail('state');

  const { id, secret } = creds(provider, env);
  const form = new URLSearchParams({
    client_id: id, client_secret: secret, code,
    redirect_uri: apiOrigin(env, url) + '/auth/' + provider + '/callback',
  });
  if (P.pkce) { form.set('grant_type', 'authorization_code'); form.set('code_verifier', st.v); }
  const tr = await fetch(P.token, {
    method: 'POST', body: form,
    headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  const tj = await tr.json().catch(() => null);
  if (!tr.ok || !tj || tj.error) { console.warn('token exchange failed', provider, tr.status, tj && tj.error); return fail('exchange'); }

  let ident;   // {sub, email}
  if (provider === 'google') {
    // the ID token came straight from Google's token endpoint over TLS, so its
    // signature needs no separate check (OIDC Core 3.1.3.7); we still pin the
    // issuer, audience and expiry
    const parts = (tj.id_token || '').split('.');
    let claims = null;
    try { claims = JSON.parse(new TextDecoder().decode(b64urlDecode(parts[1]))); } catch (e) {}
    if (!claims || !['https://accounts.google.com', 'accounts.google.com'].includes(claims.iss) ||
        claims.aud !== id || !claims.sub || claims.exp * 1000 < Date.now()) return fail('idtoken');
    ident = { sub: String(claims.sub), email: claims.email_verified ? claims.email : null };
  } else {
    const ur = await fetch('https://api.github.com/user', {
      headers: { Authorization: 'Bearer ' + tj.access_token, Accept: 'application/vnd.github+json',
                 'User-Agent': 'misterzine-api' },
    });
    const uj = await ur.json().catch(() => null);
    if (!ur.ok || !uj || !uj.id) return fail('profile');
    ident = { sub: String(uj.id), email: uj.email || null };
  }

  // find or create the user; `new` tells the site to import local favorites once
  let user = await env.DB.prepare('SELECT id FROM users WHERE provider = ? AND provider_user_id = ?')
    .bind(provider, ident.sub).first();
  let isNew = false;
  if (!user) {
    const ins = await env.DB.prepare('INSERT INTO users (provider, provider_user_id, email) VALUES (?, ?, ?)')
      .bind(provider, ident.sub, ident.email).run();
    user = { id: ins.meta.last_row_id };
    isNew = true;
  } else if (ident.email) {
    await env.DB.prepare('UPDATE users SET email = ? WHERE id = ? AND (email IS NULL OR email <> ?)')
      .bind(ident.email, user.id, ident.email).run();
  }
  const token = await createSession(env, user.id);
  return new Response(null, {
    status: 302,
    headers: {
      Location: env.SITE_ORIGIN + '/auth/#t=' + token + '&new=' + (isNew ? 1 : 0) + '&r=' + encodeURIComponent(st.r),
      'Set-Cookie': clearCookie(), 'Cache-Control': 'no-store',
    },
  });
}

// --- state cookie (HMAC-signed, self-contained) --------------------------------

async function hmacKey(env) {
  if (!env.SESSION_SECRET) throw new Error('SESSION_SECRET not configured');
  return crypto.subtle.importKey('raw', enc.encode(env.SESSION_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
}
async function signCookie(env, obj) {
  const body = b64url(enc.encode(JSON.stringify(obj)));
  const sig = b64url(new Uint8Array(await crypto.subtle.sign('HMAC', await hmacKey(env), enc.encode(body))));
  return body + '.' + sig;
}
async function verifyCookie(env, value) {
  const [body, sig] = value.split('.');
  if (!body || !sig) return null;
  const ok = await crypto.subtle.verify('HMAC', await hmacKey(env), b64urlDecode(sig), enc.encode(body));
  if (!ok) return null;
  try { return JSON.parse(new TextDecoder().decode(b64urlDecode(body))); } catch (e) { return null; }
}
const clearCookie = () => COOKIE + '=; Path=/auth; Max-Age=0; HttpOnly; Secure; SameSite=Lax';
function parseCookies(s) {
  const out = {};
  for (const part of s.split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}

// --- small helpers -------------------------------------------------------------

// the origin registered with the OAuth providers as redirect_uri; pinned by
// config so a request arriving through an odd host header can't change it
const apiOrigin = (env, url) => env.API_ORIGIN || url.origin;

function corsHeaders(env, origin) {
  const allowed = [env.SITE_ORIGIN, ...(env.DEV_ORIGINS || '').split(',')].map(s => s && s.trim()).filter(Boolean);
  if (!origin || !allowed.includes(origin)) return {};
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-Confirm',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
async function readJSON(request) {
  try { return await request.json(); } catch (e) { return null; }
}
function b64url(bytes) {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function b64urlDecode(s) {
  s = s.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(s + '='.repeat((4 - s.length % 4) % 4));
  return Uint8Array.from(bin, c => c.charCodeAt(0));
}
async function sha256bytes(str) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(str)));
}
async function sha256hex(str) {
  return [...await sha256bytes(str)].map(b => b.toString(16).padStart(2, '0')).join('');
}
