import { env, SELF } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import schema from '../schema.sql?raw';
import { addressBucket, discordMessage, feedback } from '../src/feedback.js';

const API = 'https://api.misterzine.fyi';
const SITE = 'https://misterzine.fyi';
const ADMIN = { Authorization: 'Bearer test-admin-token' };
const HOOK = 'https://discord.example/api/webhooks/1/abc';
const IP = '203.0.113.7';
const T0 = Date.parse('2026-10-07T12:00:00Z');
const MIN = 60e3;
const DAY = 864e5;

const hooked = () => ({ ...env, DISCORD_FEEDBACK_WEBHOOK: HOOK });
const rows = async () => (await env.DB.prepare('SELECT * FROM feedback ORDER BY id').all()).results;
const sha256hex = async s =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(b => b.toString(16).padStart(2, '0')).join('');

// call runs POST /feedback directly, so tests can swap bindings, the clock,
// the sender's address, the signed-in user and Discord itself. By default a
// webhook is configured and Discord answers 204, recording what it was sent.
async function call(body, { ip = IP, headers = {}, e = hooked(), now = T0, discord, user = null } = {}) {
  const sent = [];
  const fetch = discord || (async (url, init) => { sent.push({ url, init, msg: JSON.parse(init.body) }); return new Response(null, { status: 204 }); });
  const req = new Request(API + '/feedback', {
    method: 'POST',
    body: typeof body === 'string' ? body : JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', 'CF-Connecting-IP': ip, 'User-Agent': 'Mozilla/5.0 test', ...headers },
  });
  const res = await feedback(req, e, 'POST', '/feedback', { now, fetch, authenticate: async () => user });
  return { status: res.status, res, out: await res.json(), sent };
}

const exportAs = (headers, query = '') =>
  feedback(new Request(API + '/feedback/export' + query, { headers }), env, 'GET', '/feedback/export');

beforeAll(async () => {
  // the real schema file, statement by statement (comments first: one holds a semicolon)
  const stmts = schema.replace(/--.*$/gm, '').split(';').map(s => s.trim()).filter(Boolean);
  await env.DB.batch(stmts.map(s => env.DB.prepare(s)));
});

beforeEach(async () => {
  await env.DB.batch(['feedback', 'sessions', 'favorites', 'users'].map(t => env.DB.prepare('DELETE FROM ' + t)));
});

describe('a message', () => {
  it('is stored with what the form sent and forwarded to Discord as one embed', async () => {
    const body = { text: 'The Galaga row says 1982, the flyer says 1981.', contact: 'someone#1234',
                   page: SITE + '/releases/?q=galaga', key: 'galaga_jt', theme: 'eva' };
    const r = await call(body);
    expect(r.status).toBe(201);
    expect(r.out).toEqual({ ok: true });

    const [row, ...rest] = await rows();
    expect(rest).toHaveLength(0);
    expect(row).toMatchObject({
      created_at: '2026-10-07T12:00:00Z', text: body.text, contact: 'someone#1234', page: body.page,
      row_key: 'galaga_jt', theme: 'eva', account_id: null, user_agent: 'Mozilla/5.0 test', discord_ok: 1,
    });
    expect(row.ip_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(row.ip_hash).not.toBe(await sha256hex(IP)); // keyed, not a plain hash of the address

    expect(r.sent).toHaveLength(1);
    const { url, init, msg } = r.sent[0];
    expect(url).toBe(HOOK);
    expect(init.method).toBe('POST');
    expect(msg.allowed_mentions).toEqual({ parse: [] });
    expect(msg.embeds).toHaveLength(1);
    const e = msg.embeds[0];
    expect(e.title).toBe('Feedback #' + row.id);
    expect(e.description).toBe(body.text);
    const f = Object.fromEntries(e.fields.map(x => [x.name, x.value]));
    expect(f).toEqual({
      Page: body.page,
      Row: '[galaga_jt](https://misterzine.fyi/releases/#galaga_jt)',
      Contact: 'someone#1234',
      Theme: 'eva',
    });
    expect(JSON.stringify(msg)).not.toContain(IP);
  });

  it('needs only the text, and is stored when no webhook is configured', async () => {
    const r = await call({ text: 'love it' }, { e: env });
    expect(r.status).toBe(201);
    expect(r.sent).toHaveLength(0);
    const [row] = await rows();
    expect(row).toMatchObject({ text: 'love it', contact: null, page: null, row_key: null, theme: null, account_id: null, discord_ok: 0 });
  });

  it('records the account when the request is signed in', async () => {
    const r = await call({ text: 'signed in' }, { user: { id: 42, provider: 'github' } });
    expect(r.status).toBe(201);
    expect((await rows())[0].account_id).toBe(42);
    const f = r.sent[0].msg.embeds[0].fields;
    expect(f).toContainEqual({ name: 'Account', value: 'signed in as 42 (github)', inline: true });
  });

  it('still answers success when Discord fails, and leaves discord_ok at 0', async () => {
    const broken = [
      async () => { throw new TypeError('network'); },
      async () => new Response('{"message":"Unknown Webhook"}', { status: 404 }),
      async () => new Response('slow down', { status: 429 }),
    ];
    for (const discord of broken) expect((await call({ text: 'still here' }, { discord })).status).toBe(201);
    const all = await rows();
    expect(all).toHaveLength(3);
    expect(all.map(x => x.discord_ok)).toEqual([0, 0, 0]);
  });

  it('trims the text, normalises line ends and drops control characters', async () => {
    await call({ text: '  line one\r\nline two\u0007\u0000  ', contact: '  a  b \n c ' });
    const [row] = await rows();
    expect(row.text).toBe('line one\nline two');
    expect(row.contact).toBe('a b c');
  });
});

describe('what a message must be', () => {
  it('refuses no text, blank text, and text over 4000 characters', async () => {
    for (const [body, error] of [
      [{}, 'no_text'], [{ text: '' }, 'no_text'], [{ text: '  \n\t ' }, 'no_text'], [{ text: 42 }, 'no_text'],
      [{ text: 'a'.repeat(4001) }, 'text_too_long'],
    ]) {
      const r = await call(body);
      expect([r.status, r.out.error], JSON.stringify(body).slice(0, 40)).toEqual([400, error]);
    }
    expect(await rows()).toHaveLength(0);
    expect((await call({ text: 'a'.repeat(4000) })).status).toBe(201);
  });

  it('refuses more than five links, counting the contact box', async () => {
    const links = n => Array.from({ length: n }, (_, i) => 'https://spam' + i + '.example').join(' ');
    expect((await call({ text: links(6) })).out.error).toBe('too_many_links');
    expect((await call({ text: links(4) + ' www.more.example', contact: 'http://x.example' })).out.error).toBe('too_many_links');
    expect((await call({ text: links(5) })).status).toBe(201);
    expect(await rows()).toHaveLength(1);
  });

  it('refuses a contact over 200 characters, or one that is not text', async () => {
    expect((await call({ text: 'hi', contact: 'c'.repeat(201) })).out.error).toBe('contact_too_long');
    expect((await call({ text: 'hi', contact: 5 })).out.error).toBe('bad_contact');
    expect((await call({ text: 'hi', contact: 'c'.repeat(200) })).status).toBe(201);
    expect((await call({ text: 'hi', contact: '   ' })).status).toBe(201);
    expect((await rows()).map(x => x.contact)).toEqual(['c'.repeat(200), null]);
  });

  it('refuses a body that is not a JSON object, or is too large', async () => {
    for (const body of ['not json', '[1]', 'null', '"text"']) {
      const r = await call(body);
      expect([r.status, r.out.error], body).toEqual([400, 'bad_json']);
    }
    expect((await call({ text: 'x', pad: 'p'.repeat(40000) })).status).toBe(413);
    expect(await rows()).toHaveLength(0);
  });

  it('drops a page, key or theme that does not fit, and keeps the message', async () => {
    const extras = [
      { page: 'https://evil.example/releases/' }, { page: 'javascript:alert(1)' }, { page: 7 },
      { key: 'not a key!' }, { key: 'k'.repeat(65) }, { theme: 't'.repeat(33) }, { theme: '<b>' },
    ];
    // one address each: eight messages from one would pass the 10-minute limit
    for (const [i, extra] of extras.entries())
      expect((await call({ text: 'hi', ...extra }, { ip: '198.51.100.' + i })).status).toBe(201);
    const all = await rows();
    expect(all).toHaveLength(7);
    for (const x of all) expect([x.page, x.row_key, x.theme]).toEqual([null, null, null]);

    await call({ text: 'long page', page: SITE + '/releases/?fav=' + 'a,'.repeat(400) }, { ip: '198.51.100.99' });
    const long = (await rows()).at(-1).page;
    expect(long).toHaveLength(500);
    expect(long.startsWith(SITE + '/releases/?fav=a,a,')).toBe(true);
  });
});

describe('the honeypot', () => {
  it('answers success for a filled website field, and stores and sends nothing', async () => {
    const r = await call({ text: 'buy now', website: 'http://spam.example' });
    expect([r.status, r.out]).toEqual([201, { ok: true }]);
    expect(r.sent).toHaveLength(0);
    expect(await rows()).toHaveLength(0);
  });

  it('ignores an empty or blank website field', async () => {
    expect((await call({ text: 'a', website: '' })).status).toBe(201);
    expect((await call({ text: 'b', website: '  ' })).status).toBe(201);
    expect(await rows()).toHaveLength(2);
  });
});

describe('rate limits', () => {
  it('takes 5 in 10 minutes from one address, then 429 until the oldest is 10 minutes old', async () => {
    for (let i = 0; i < 5; i++) expect((await call({ text: 'm' + i }, { now: T0 + i * MIN })).status).toBe(201);
    const r = await call({ text: 'one more' }, { now: T0 + 5 * MIN });
    expect([r.status, r.out]).toEqual([429, { error: 'rate_limited', retry_after: 300 }]);
    expect(r.res.headers.get('Retry-After')).toBe('300');
    expect(r.sent).toHaveLength(0);
    expect((await call({ text: 'someone else' }, { ip: '198.51.100.9', now: T0 + 5 * MIN })).status).toBe(201);
    expect((await call({ text: 'later' }, { now: T0 + 10 * MIN + 1000 })).status).toBe(201);
    expect(await rows()).toHaveLength(7);
  });

  it('takes 30 in any 24 hours', async () => {
    const step = 15 * MIN; // one per quarter hour stays inside the 10-minute limit
    for (let i = 0; i < 30; i++) expect((await call({ text: 'd' + i }, { now: T0 + i * step })).status).toBe(201);
    const r = await call({ text: 'too many' }, { now: T0 + 30 * step });
    expect(r.status).toBe(429);
    expect(r.out.retry_after).toBe((DAY - 30 * step) / 1000);
    expect((await call({ text: 'next day' }, { now: T0 + DAY + 1000 })).status).toBe(201);
  });

  it('counts one IPv6 household (/64) as one sender', async () => {
    const same = ['2001:db8:1:2::a', '2001:DB8:1:2:ffff::1', '2001:db8:0001:0002:abcd:0:0:9', '2001:db8:1:2::b', '2001:db8:1:2::c'];
    for (const ip of same) expect((await call({ text: ip }, { ip })).status).toBe(201);
    expect((await call({ text: 'x' }, { ip: '2001:db8:1:2:9::9' })).status).toBe(429);
    expect((await call({ text: 'x' }, { ip: '2001:db8:1:3::a' })).status).toBe(201);
  });

  it('does not count refused or honeypot requests against the sender', async () => {
    for (let i = 0; i < 6; i++) await call({ text: ' ' });
    for (let i = 0; i < 6; i++) await call({ text: 'bot', website: 'x' });
    for (let i = 0; i < 5; i++) expect((await call({ text: 'real ' + i })).status).toBe(201);
  });

  it('buckets addresses the way it says', () => {
    expect(addressBucket('203.0.113.7')).toBe('203.0.113.7');
    expect(addressBucket('::ffff:203.0.113.7')).toBe('203.0.113.7');
    expect(addressBucket('2001:DB8:0001:0002::1')).toBe('2001:db8:1:2::/64');
    expect(addressBucket('2001:db8:1:2:3:4:5:6')).toBe('2001:db8:1:2::/64');
    expect(addressBucket('fe80::1%eth0')).toBe('fe80:0:0:0::/64');
    expect(addressBucket('::1')).toBe('0:0:0:0::/64');
  });
});

describe('where it may come from', () => {
  it('refuses a browser on another site, and takes the site and plain clients', async () => {
    const r = await call({ text: 'x' }, { headers: { Origin: 'https://evil.example' } });
    expect([r.status, r.out.error]).toEqual([403, 'origin']);
    expect((await call({ text: 'from the site' }, { headers: { Origin: SITE } })).status).toBe(201);
    expect((await call({ text: 'from curl' })).status).toBe(201);
    expect((await call({ text: 'dev' }, { headers: { Origin: 'http://localhost:8012' }, e: { ...hooked(), DEV_ORIGINS: 'http://localhost:8012' } })).status).toBe(201);
    expect(await rows()).toHaveLength(3);
  });

  it('answers 503 when switched off', async () => {
    const r = await call({ text: 'x' }, { e: { ...env, FEEDBACK_ENABLED: '0' } });
    expect([r.status, r.out.error]).toEqual([503, 'disabled']);
  });
});

describe('through the Worker', () => {
  it('answers the preflight and the post with CORS for the site', async () => {
    const pre = await SELF.fetch(API + '/feedback', {
      method: 'OPTIONS', headers: { Origin: SITE, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type' },
    });
    expect(pre.status).toBe(204);
    expect(pre.headers.get('Access-Control-Allow-Origin')).toBe(SITE);
    expect(pre.headers.get('Access-Control-Allow-Methods')).toContain('POST');
    expect(pre.headers.get('Access-Control-Allow-Headers')).toContain('Content-Type');

    const r = await SELF.fetch(API + '/feedback', {
      method: 'POST', headers: { Origin: SITE, 'Content-Type': 'application/json' }, body: JSON.stringify({ text: 'via the worker' }),
    });
    expect(r.status).toBe(201);
    expect(r.headers.get('Access-Control-Allow-Origin')).toBe(SITE);
    expect(await r.json()).toEqual({ ok: true });
    expect((await rows())[0]).toMatchObject({ text: 'via the worker', account_id: null, discord_ok: 0 });
  });

  it('records the account behind a real session token, and treats a bad token as anonymous', async () => {
    const u = await env.DB.prepare("INSERT INTO users (provider, provider_user_id) VALUES ('github', '123')").run();
    const id = u.meta.last_row_id;
    const token = 'T'.repeat(43);
    await env.DB.prepare('INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)').bind(await sha256hex(token), id).run();
    const post = auth => SELF.fetch(API + '/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: auth }, body: JSON.stringify({ text: auth.slice(0, 12) }),
    });
    expect((await post('Bearer ' + token)).status).toBe(201);
    expect((await post('Bearer ' + 'U'.repeat(43))).status).toBe(201);
    expect((await post('Bearer short')).status).toBe(201);
    expect((await rows()).map(x => x.account_id)).toEqual([id, null, null]);
  });

  it('serves the export to the developer only', async () => {
    await SELF.fetch(API + '/feedback', { method: 'POST', body: JSON.stringify({ text: 'one' }) });
    expect((await SELF.fetch(API + '/feedback/export')).status).toBe(401);
    const r = await SELF.fetch(API + '/feedback/export', { headers: ADMIN });
    expect(r.status).toBe(200);
    expect((await r.json()).feedback.map(x => x.text)).toEqual(['one']);
    expect((await SELF.fetch(API + '/feedback')).status).toBe(404); // GET of the form route
  });
});

describe('the export', () => {
  it('gives every message oldest first, from an id on with ?since', async () => {
    for (const text of ['first', 'second', 'third']) await call({ text, contact: text + '@example.com' });
    for (const headers of [{}, { Authorization: 'Bearer wrong' }, { Authorization: 'test-admin-token' }])
      expect((await exportAs(headers)).status).toBe(401);
    const all = (await (await exportAs(ADMIN)).json()).feedback;
    expect(all.map(x => x.text)).toEqual(['first', 'second', 'third']);
    expect(Object.keys(all[0]).sort()).toEqual(
      ['account_id', 'contact', 'created_at', 'discord_ok', 'id', 'ip_hash', 'page', 'row_key', 'text', 'theme', 'user_agent']);
    const later = (await (await exportAs(ADMIN, '?since=' + all[0].id)).json()).feedback;
    expect(later.map(x => x.text)).toEqual(['second', 'third']);
  });

  it('refuses everyone when no admin token is configured', async () => {
    const r = await feedback(new Request(API + '/feedback/export', { headers: { Authorization: 'Bearer ' } }),
      { ...env, REPORTS_TOKEN: '' }, 'GET', '/feedback/export');
    expect(r.status).toBe(401);
  });
});

describe('the Discord message', () => {
  it('fits Discord limits however long the fields, and makes no masked links', () => {
    const row = {
      id: 123456, created_at: '2026-10-07T12:00:00Z', text: '['.repeat(4000),
      contact: '[x](https://evil.example)' + 'c'.repeat(175), page: SITE + '/releases/?' + 'a'.repeat(475),
      key: 'k'.repeat(64), theme: 't'.repeat(32), account_id: 123456, provider: 'google',
    };
    const e = discordMessage(row, SITE).embeds[0];
    const total = e.title.length + e.description.length + e.fields.reduce((n, f) => n + f.name.length + f.value.length, 0);
    expect(e.description.length).toBeLessThanOrEqual(4096);
    expect(total).toBeLessThanOrEqual(6000);
    for (const f of e.fields) expect(f.value.length).toBeLessThanOrEqual(1024);
    expect(e.description.endsWith('...')).toBe(true);
    expect(e.fields.find(f => f.name === 'Contact').value.startsWith('\\[x\\](https://evil.example)')).toBe(true);

    const plain = discordMessage({ ...row, text: 'see [this](https://x.example)', contact: null }, SITE).embeds[0];
    expect(plain.description).toBe('see \\[this\\](https://x.example)');
  });

  it('never cuts an emoji in half when it has to shorten the text', () => {
    // escaped, the brackets take 4090 characters, so the emoji straddles the cut
    const text = '['.repeat(2045) + 'xy' + '\u{1F600}' + 'z'.repeat(20);
    const d = discordMessage({ id: 1, created_at: '2026-10-07T12:00:00Z', text }, SITE).embeds[0].description;
    expect(d.endsWith('xy...')).toBe(true);
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(d)).toBe(false);
  });
});
