import { env, SELF } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { MAGIC, normalizeCode, reports } from '../src/reports.js';

const ADMIN = { Authorization: 'Bearer test-admin-token' };
const BODY = MAGIC + '\nApp: misterzine v1.1.2-dev (abc1234, 2026-09-22)\n\nSYSTEM\n...\n';
const CODE_RE = /^[0-9A-HJKMNP-TV-Z]{4}$/;
const DAY = 86400000;

// st reads the body before the status: an unread R2 stream breaks the test
// runner's per-test storage isolation.
const st = async r => { await (await r).arrayBuffer(); return (await r).status; };

// call runs one route directly, so tests can swap bindings and the clock.
const call = (method, path, { body, headers = {}, e = env, now } = {}) =>
  reports(new Request('https://api.misterzine.fyi' + path, { method, body, headers }), e, method, path, now);

async function send(body = BODY, e = env) {
  const r = await call('POST', '/reports', { body, e });
  expect(r.status).toBe(201);
  const { code } = await r.json();
  expect(code).toMatch(CODE_RE);
  return code;
}

beforeEach(async () => {
  const { objects } = await env.REPORTS.list();
  for (const o of objects) await env.REPORTS.delete(o.key);
});

describe('upload and read', () => {
  it('stores a report under a code the developer can read, list and delete', async () => {
    const code = await send();
    const r = await call('GET', '/reports/' + code, { headers: ADMIN });
    expect(r.status).toBe(200);
    expect(r.headers.get('Content-Type')).toContain('text/plain');
    expect(await r.text()).toBe(BODY);

    const list = await (await call('GET', '/reports', { headers: ADMIN })).json();
    expect(list.reports).toHaveLength(1);
    expect(list.reports[0]).toMatchObject({ code, size: BODY.length, app: 'misterzine v1.1.2-dev (abc1234, 2026-09-22)' });

    // a code typed by a person: lower case, a dash, O for zero
    const typed = (code.slice(0, 4) + '-' + code.slice(4)).toLowerCase().replace(/0/g, 'o');
    expect((await st(call('GET', '/reports/' + typed, { headers: ADMIN })))).toBe(200);

    expect((await st(call('DELETE', '/reports/' + code, { headers: ADMIN })))).toBe(204);
    expect((await st(call('GET', '/reports/' + code, { headers: ADMIN })))).toBe(404);
  });

  it('answers through the Worker, and the account service still does', async () => {
    const r = await SELF.fetch('https://api.misterzine.fyi/reports', { method: 'POST', body: BODY });
    expect(r.status).toBe(201);
    expect((await r.json()).code).toMatch(CODE_RE);
    expect((await st(SELF.fetch('https://api.misterzine.fyi/')))).toBe(200);
    expect((await st(SELF.fetch('https://api.misterzine.fyi/favorites')))).toBe(401);
  });
});

describe('only the developer reads', () => {
  it('refuses the list and a report without the right token', async () => {
    const code = await send();
    for (const headers of [{}, { Authorization: 'Bearer wrong' }, { Authorization: 'test-admin-token' }]) {
      expect((await st(call('GET', '/reports', { headers })))).toBe(401);
      expect((await st(call('GET', '/reports/' + code, { headers })))).toBe(401);
      expect((await st(call('DELETE', '/reports/' + code, { headers })))).toBe(401);
    }
    expect((await st(call('GET', '/reports/' + code, { headers: ADMIN })))).toBe(200);
  });

  it('refuses everything when no token is configured', async () => {
    const code = await send();
    const e = { ...env, REPORTS_TOKEN: '' };
    expect((await st(call('GET', '/reports/' + code, { headers: { Authorization: 'Bearer ' }, e })))).toBe(401);
  });
});

describe('what an upload must be', () => {
  it('turns away text that is not a report', async () => {
    expect((await st(call('POST', '/reports', { body: 'hello' })))).toBe(400);
    expect((await st(call('POST', '/reports', { body: '' })))).toBe(400);
  });

  it('turns away a report over the size cap, by header or by body', async () => {
    const e = { ...env, REPORT_MAX_BYTES: '64' };
    const big = BODY + 'x'.repeat(100);
    expect((await st(call('POST', '/reports', { body: big, e })))).toBe(413);
    const stream = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(big)); c.close(); } });
    expect(await st(reports(new Request('https://api.misterzine.fyi/reports', { method: 'POST', body: stream, duplex: 'half' }), e, 'POST', '/reports'))).toBe(413);
    expect((await env.REPORTS.list()).objects).toHaveLength(0);
  });

  it('answers 503 when uploads are switched off', async () => {
    expect((await st(call('POST', '/reports', { body: BODY, e: { ...env, REPORTS_ENABLED: '0' } })))).toBe(503);
  });

  it('answers 429 when the sender is over the rate limit', async () => {
    const seen = [];
    const limiter = { limit: async ({ key }) => { seen.push(key); return { success: seen.length <= 3 }; } };
    const e = { ...env, REPORT_LIMIT: limiter };
    for (let i = 0; i < 3; i++) await send(BODY, e);
    expect((await st(call('POST', '/reports', { body: BODY, e })))).toBe(429);
  });
});

describe('thirty days', () => {
  it('stops serving and listing a report once it is 30 days old', async () => {
    const code = await send();
    const later = Date.now() + 31 * DAY;
    expect((await st(call('GET', '/reports/' + code, { headers: ADMIN, now: later })))).toBe(404);
    expect((await (await call('GET', '/reports', { headers: ADMIN, now: later })).json()).reports).toHaveLength(0);
    const soon = Date.now() + 29 * DAY;
    expect((await st(call('GET', '/reports/' + code, { headers: ADMIN, now: soon })))).toBe(200);
  });
});

describe('codes', () => {
  it('reads what people type and rejects the rest', () => {
    expect(normalizeCode('k7q2')).toBe('K7Q2');
    expect(normalizeCode('K7-Q2')).toBe('K7Q2');
    expect(normalizeCode(' K7Q2 ')).toBe('K7Q2');
    expect(normalizeCode('oIl0')).toBe('0110');
    expect(normalizeCode('K7Q')).toBe('');
    expect(normalizeCode('K7Q2X')).toBe('');
    expect(normalizeCode('K7QU')).toBe('');
    expect(normalizeCode('7K2Q9XMB')).toBe(''); // the first service's length is gone
    expect(normalizeCode('../../x')).toBe('');
  });
});

describe('claiming a code', () => {
  it('never lets a second upload take a code that is held', async () => {
    const opts = { onlyIf: new Headers({ 'If-None-Match': '*' }) };
    expect(await env.REPORTS.put('r/K7Q2.txt', 'first', opts)).not.toBeNull();
    expect(await env.REPORTS.put('r/K7Q2.txt', 'second', opts)).toBeNull();
    const kept = await env.REPORTS.get('r/K7Q2.txt');
    expect(await kept.text()).toBe('first');
  });
});
