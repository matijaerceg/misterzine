import { env, SELF } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import schema from '../schema.sql?raw';

// The site notice (docs/theme.js NOTICE): a signed-in visitor's close is kept
// on the account, so GET /me can tell the other browsers to skip it.
const API = 'https://api.misterzine.fyi';
const TOKEN = 'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMN';
const sha256hex = async s =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(b => b.toString(16).padStart(2, '0')).join('');
const as = (path, init = {}) =>
  SELF.fetch(API + path, { ...init, headers: { Authorization: 'Bearer ' + TOKEN, 'Content-Type': 'application/json', ...(init.headers || {}) } });

beforeAll(async () => {
  const stmts = schema.replace(/--.*$/gm, '').split(';').map(s => s.trim()).filter(Boolean);
  await env.DB.batch(stmts.map(s => env.DB.prepare(s)));
});

beforeEach(async () => {
  await env.DB.batch(['feedback', 'sessions', 'favorites', 'users'].map(t => env.DB.prepare('DELETE FROM ' + t)));
  await env.DB.prepare("INSERT INTO users (id, provider, provider_user_id) VALUES (1, 'github', 'x')").run();
  await env.DB.prepare('INSERT INTO sessions (token_hash, user_id) VALUES (?, 1)').bind(await sha256hex(TOKEN)).run();
});

describe('the site notice', () => {
  it('is unseen on a fresh account, and remembered once closed', async () => {
    expect((await (await as('/me')).json()).notice).toBeNull();
    const put = await as('/me/notice', { method: 'PUT', body: JSON.stringify({ id: 'faster-tracker-2026-10' }) });
    expect(put.status).toBe(204);
    expect((await (await as('/me')).json()).notice).toBe('faster-tracker-2026-10');
  });
  it('keeps only the latest close', async () => {
    await as('/me/notice', { method: 'PUT', body: JSON.stringify({ id: 'one' }) });
    await as('/me/notice', { method: 'PUT', body: JSON.stringify({ id: 'two' }) });
    expect((await (await as('/me')).json()).notice).toBe('two');
  });
  it('refuses an id that is not a short slug, and anyone not signed in', async () => {
    for (const id of ['', 'Has Space', 'x'.repeat(41), 7, null])
      expect((await as('/me/notice', { method: 'PUT', body: JSON.stringify({ id }) })).status).toBe(400);
    const anon = await SELF.fetch(API + '/me/notice', { method: 'PUT', body: JSON.stringify({ id: 'one' }) });
    expect(anon.status).toBe(401);
    expect((await (await as('/me')).json()).notice).toBeNull();
  });
});
