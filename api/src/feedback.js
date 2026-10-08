// Site feedback: the feedback form on misterzine.fyi posts a short message
// here. Every message is kept in D1 (table `feedback`, see schema.sql) and
// then forwarded to a private Discord channel through a webhook (the Worker
// secret DISCORD_FEEDBACK_WEBHOOK). Discord is a notification only: when the
// webhook is missing or fails, the message is still stored and the visitor
// still sees success, with discord_ok left at 0.
//
//   POST /feedback          JSON {text, contact?, page?, key?, theme?, website?}
//                           201 {ok: true}
//   GET  /feedback/export   admin: {feedback: [...]} oldest first, ?since=<id>
//
// What is kept about the sender: an HMAC of their address (the key is
// SESSION_SECRET, so the hash cannot be reversed by trying every address;
// IPv6 is cut to its /64 first, one household), the User-Agent cut to 256
// characters, the account id when the request carries a valid session, and
// whatever they type into the contact box. Never the raw address.
//
// Abuse limits, per address hash, counted over stored messages: 5 in any 10
// minutes and 30 in any 24 hours (429 with retry_after). The check and the
// insert are one SQL statement, so two requests at once cannot both slip
// under a limit. A non-empty `website` field (a honeypot the form hides from
// people) gets the normal success answer and nothing is stored. A request
// from a browser on another site (an Origin header that is not the site's)
// is refused, so no other page can make its visitors post here.
// FEEDBACK_ENABLED other than "1" turns the form off (503).
//
// Admin export takes `Authorization: Bearer <REPORTS_TOKEN>`, the same
// developer key as the device reports.

import { isAdmin, readCapped } from './reports.js';

export const TEXT_MAX = 4000;          // UTF-16 units, the same count as a textarea's maxlength
export const CONTACT_MAX = 200;
export const PAGE_MAX = 500;
export const THEME_RE = /^[A-Za-z0-9_-]{1,32}$/;
export const KEY_RE = /^[A-Za-z0-9_-]{1,64}$/;  // release tracker row keys (data.json `k`)
export const MAX_LINKS = 5;
export const LIMITS = [                // [messages, window in ms]
  [5, 10 * 60e3],
  [30, 24 * 3600e3],
];
const BODY_MAX = 32768;                // bytes; 4000 characters of any script fit easily
const UA_MAX = 256;
const DISCORD_TIMEOUT_MS = 5000;
const enc = new TextEncoder();

// feedback answers every /feedback route. opts: now (ms, for tests),
// fetch (the Discord call, for tests), authenticate (() => user row or null).
export async function feedback(request, env, m, p, opts = {}) {
  const now = opts.now ?? Date.now();
  if (p === '/feedback' && m === 'POST') return submit(request, env, now, opts);
  if (p === '/feedback/export' && m === 'GET') {
    if (!(await isAdmin(request, env))) return json({ error: 'unauthorized' }, 401);
    const since = parseInt(new URL(request.url).searchParams.get('since'), 10) || 0;
    const { results } = await env.DB.prepare('SELECT * FROM feedback WHERE id > ? ORDER BY id').bind(since).all();
    return json({ feedback: results });
  }
  return json({ error: 'not_found' }, 404);
}

async function submit(request, env, now, opts) {
  if (env.FEEDBACK_ENABLED !== '1') return json({ error: 'disabled' }, 503);
  const origin = request.headers.get('Origin');
  if (origin && !allowedOrigins(env).includes(origin)) return json({ error: 'origin' }, 403);

  if ((parseInt(request.headers.get('Content-Length'), 10) || 0) > BODY_MAX) return json({ error: 'too_large' }, 413);
  const bytes = await readCapped(request, BODY_MAX);
  if (!bytes) return json({ error: 'too_large' }, 413);
  let body = null;
  try { body = JSON.parse(new TextDecoder().decode(bytes)); } catch (e) {}
  if (!body || typeof body !== 'object' || Array.isArray(body)) return json({ error: 'bad_json' }, 400);

  // honeypot: people never see the field, so anything in it is a bot
  if (body.website != null && String(body.website).trim() !== '') return json({ ok: true }, 201);

  const v = validate(body, env);
  if (v.error) return json({ error: v.error }, 400);

  const user = opts.authenticate ? await opts.authenticate().catch(() => null) : null;
  const ipHash = await hashAddress(env, request.headers.get('CF-Connecting-IP') || 'unknown');
  const ua = (request.headers.get('User-Agent') || '').slice(0, UA_MAX) || null;
  const created = iso(now);

  // check both limits and insert in one statement: D1 runs writes one at a
  // time, so concurrent requests cannot all pass the count
  const [[n1, w1], [n2, w2]] = LIMITS;
  const ins = await env.DB.prepare(
    'INSERT INTO feedback (created_at, text, contact, page, row_key, theme, account_id, ip_hash, user_agent, discord_ok) ' +
    'SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, 0 ' +
    'WHERE (SELECT COUNT(*) FROM feedback WHERE ip_hash = ?8 AND created_at > ?10) < ?11 ' +
    'AND (SELECT COUNT(*) FROM feedback WHERE ip_hash = ?8 AND created_at > ?12) < ?13'
  ).bind(created, v.text, v.contact, v.page, v.key, v.theme, user ? user.id : null, ipHash, ua,
         iso(now - w1), n1, iso(now - w2), n2).run();

  if (!ins.meta.changes) {
    const wait = await retryAfter(env, ipHash, now);
    const res = json({ error: 'rate_limited', retry_after: wait }, 429);
    res.headers.set('Retry-After', String(wait));
    return res;
  }

  const row = { id: ins.meta.last_row_id, created_at: created, ...v, account_id: user ? user.id : null,
                provider: user ? user.provider : null };
  const hook = env.DISCORD_FEEDBACK_WEBHOOK;
  if (hook) {
    let ok = false;
    try {
      const r = await (opts.fetch || fetch)(hook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(discordMessage(row, env.SITE_ORIGIN || 'https://misterzine.fyi')),
        signal: AbortSignal.timeout(DISCORD_TIMEOUT_MS),
      });
      ok = r.ok;
      if (!ok) console.warn('discord webhook failed', r.status);
      if (r.body) await r.body.cancel();
    } catch (e) {
      console.warn('discord webhook error', e && e.name);
    }
    if (ok) await env.DB.prepare('UPDATE feedback SET discord_ok = 1 WHERE id = ?').bind(row.id).run();
  }
  return json({ ok: true }, 201);
}

// validate returns the cleaned fields, or {error}. The visitor's own words
// (text, contact) are refused when wrong so the form can say why; the
// metadata the page fills in (page, key, theme) is dropped when it does not
// fit, so a page-side glitch never costs a message.
export function validate(body, env) {
  if (typeof body.text !== 'string') return { error: 'no_text' };
  const text = clean(body.text).trim();
  if (!text) return { error: 'no_text' };
  if (text.length > TEXT_MAX) return { error: 'text_too_long' };

  let contact = null;
  if (body.contact != null) {
    if (typeof body.contact !== 'string') return { error: 'bad_contact' };
    contact = clean(body.contact).replace(/\s+/g, ' ').trim() || null;
    if (contact && contact.length > CONTACT_MAX) return { error: 'contact_too_long' };
  }
  const links = (text + '\n' + (contact || '')).match(/\b(?:https?:\/\/|www\.)\S/gi);
  if (links && links.length > MAX_LINKS) return { error: 'too_many_links' };

  let page = null;
  if (typeof body.page === 'string' && body.page) {
    try {
      const u = new URL(body.page);
      if (allowedOrigins(env).includes(u.origin)) page = u.href.slice(0, PAGE_MAX);
    } catch (e) {}
  }
  const key = typeof body.key === 'string' && KEY_RE.test(body.key) ? body.key : null;
  const theme = typeof body.theme === 'string' && THEME_RE.test(body.theme) ? body.theme : null;
  return { text, contact, page, key, theme };
}

// clean drops control characters other than newline and tab, and turns
// Windows/old-Mac line ends into \n.
const clean = s => s.replace(/\r\n?/g, '\n').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, '');

// hashAddress is the stored stand-in for the sender's address: HMAC-SHA256
// keyed with SESSION_SECRET (an address alone has too few possibilities for a
// plain hash), over the IPv4 address or the IPv6 /64.
export async function hashAddress(env, ip) {
  if (!env.SESSION_SECRET) throw new Error('SESSION_SECRET not configured');
  const key = await crypto.subtle.importKey('raw', enc.encode(env.SESSION_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode('feedback-ip\n' + addressBucket(ip)));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, '0')).join('');
}

// addressBucket is what the limits count: an IPv4 address as is (also when
// written IPv4-mapped), an IPv6 address cut to its first four groups.
export function addressBucket(ip) {
  ip = String(ip).trim().toLowerCase().replace(/%.*$/, '');
  const v4 = ip.match(/(\d{1,3}(?:\.\d{1,3}){3})$/);
  if (v4) return v4[1];
  if (!ip.includes(':')) return ip;
  const [head, tail] = ip.split('::');
  const h = head ? head.split(':') : [];
  const t = tail ? tail.split(':') : [];
  const groups = ip.includes('::') ? [...h, ...Array(Math.max(0, 8 - h.length - t.length)).fill('0'), ...t] : h;
  return groups.slice(0, 4).map(g => (parseInt(g, 16) || 0).toString(16)).join(':') + '::/64';
}

// retryAfter is the number of seconds until the sender is under every limit.
async function retryAfter(env, ipHash, now) {
  const longest = Math.max(...LIMITS.map(([, w]) => w));
  const most = Math.max(...LIMITS.map(([n]) => n));
  const { results } = await env.DB.prepare(
    'SELECT created_at FROM feedback WHERE ip_hash = ? AND created_at > ? ORDER BY created_at DESC LIMIT ?'
  ).bind(ipHash, iso(now - longest), most).all();
  const ts = results.map(r => Date.parse(r.created_at));   // newest first
  let wait = 0;
  for (const [n, w] of LIMITS) {
    const inside = ts.filter(t => t > now - w);
    if (inside.length >= n) wait = Math.max(wait, inside[n - 1] + w - now);
  }
  return Math.max(1, Math.ceil(wait / 1000));
}

// discordMessage is the webhook body: one embed, no pings. Discord caps an
// embed's description at 4096 characters, a field value at 1024 and the
// whole embed at 6000, so the visitor's text gets whatever the rest leaves.
export function discordMessage(row, site) {
  const fields = [];
  if (row.page) fields.push({ name: 'Page', value: clip(row.page, 1024) });
  if (row.key) fields.push({ name: 'Row', value: '[' + row.key + '](' + site + '/releases/#' + row.key + ')', inline: true });
  if (row.contact) fields.push({ name: 'Contact', value: clip(escapeLinks(row.contact), 1024), inline: true });
  if (row.account_id != null)
    fields.push({ name: 'Account', value: 'signed in as ' + row.account_id + (row.provider ? ' (' + row.provider + ')' : ''), inline: true });
  if (row.theme) fields.push({ name: 'Theme', value: row.theme, inline: true });
  const title = 'Feedback #' + row.id;
  const used = title.length + fields.reduce((n, f) => n + f.name.length + f.value.length, 0);
  return {
    username: 'misterzine feedback',
    allowed_mentions: { parse: [] },
    embeds: [{
      title,
      description: clip(escapeLinks(row.text), Math.min(4096, 6000 - used - 50)),
      color: 0x7b4fd6,
      fields,
      timestamp: row.created_at,
    }],
  };
}

// escapeLinks stops visitor text from making Discord masked links
// ([innocent text](elsewhere)); everything else shows as typed.
const escapeLinks = s => s.replace(/([[\]])/g, '\\$1');
// clip cuts to n characters with "...", never between the two halves of an
// emoji (a lone half is invalid text that Discord may refuse)
function clip(s, n) {
  if (s.length <= n) return s;
  let k = n - 3;
  if (/[\uDC00-\uDFFF]/.test(s[k])) k--;
  return s.slice(0, k) + '...';
}
const iso = ms => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
const allowedOrigins = env => [env.SITE_ORIGIN, ...(env.DEV_ORIGINS || '').split(',')].map(s => s && s.trim()).filter(Boolean);

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
