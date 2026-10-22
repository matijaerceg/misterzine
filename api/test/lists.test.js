import { env, SELF } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import schema from '../schema.sql?raw';
import migration from '../migrations/2026-10-22-custom-lists.sql?raw';

const API = 'https://api.misterzine.fyi';
const SITE = 'https://misterzine.fyi';
const TOKENS = ['A'.repeat(43), 'B'.repeat(43)];
const FIELD_NAMES = ['id', 'title', 'description', 'byline', 'keys', 'published', 'version', 'created_at', 'updated_at'].sort();
const sha256hex = async text => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))]
  .map(byte => byte.toString(16).padStart(2, '0')).join('');
const apply = async sql => env.DB.batch(sql.replace(/--.*$/gm, '').split(';').map(s => s.trim()).filter(Boolean).map(s => env.DB.prepare(s)));
const call = (path, method = 'GET', body, account = 0, headers = {}) => SELF.fetch(API + path, {
  method, headers: { 'Content-Type': 'application/json', ...(account === null ? {} : { Authorization: 'Bearer ' + TOKENS[account] }), ...headers },
  ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
});
const create = async (value = {}, account = 0) => {
  const response = await call('/lists', 'POST', { title: 'Favourite games', keys: ['galaga', 'pacman'], ...value }, account);
  expect(response.status).toBe(201);
  return response.json();
};
const read = async (id, account = 0) => (await call('/lists/' + id, 'GET', undefined, account)).json();
const publicRead = id => call('/public/lists/' + id, 'GET', undefined, null);
const savedCount = async () => env.DB.prepare('SELECT COUNT(*) AS n FROM custom_lists').first('n');

beforeAll(async () => {
  await apply(schema);
  await apply(migration);
  await apply(migration); // both schema and the upgrade must be safe to re-run
});
beforeEach(async () => {
  await env.DB.batch(['custom_lists', 'feedback', 'sessions', 'favorites', 'users'].map(table => env.DB.prepare('DELETE FROM ' + table)));
  for (let index = 0; index < TOKENS.length; index++) {
    await env.DB.prepare('INSERT INTO users (id, provider, provider_user_id, email) VALUES (?, ?, ?, ?)')
      .bind(index + 1, 'github', 'private-provider-id-' + index, 'private-' + index + '@example.com').run();
    await env.DB.prepare('INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)').bind(await sha256hex(TOKENS[index]), index + 1).run();
  }
});

describe('own lists', () => {
  it('creates a draft with a stable id, exact ordered row keys and explicit public byline', async () => {
    const list = await create({ title: '  Curated choices  ', keys: ['Core_A', 'game-b', 'Core_A', 'core_a'], byline: '  Matija  ' });
    expect(list).toMatchObject({ title: 'Curated choices', keys: ['Core_A', 'game-b', 'core_a'], byline: 'Matija',
      description: '', published: false, version: 1 });
    expect(list.id).toMatch(/^[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{12}$/);
    expect(Object.keys(list).sort()).toEqual(FIELD_NAMES);
    expect(Number.isFinite(Date.parse(list.created_at))).toBe(true);
    expect(await read(list.id.toLowerCase())).toEqual(list);
    expect((await publicRead(list.id)).status).toBe(404);
    const index = await (await call('/lists')).json();
    const { keys, ...summary } = list;
    expect(index).toEqual({ lists: [{ ...summary, count: 3 }] });
  });

  it('always starts private, even if the client supplies publish or account fields', async () => {
    const list = await create({ published: true, user_id: 2, version: 400, email: 'unwanted@example.com' });
    expect(list).toMatchObject({ published: false, version: 1, byline: '' });
    expect((await publicRead(list.id)).status).toBe(404);
    expect((await (await call('/lists', 'GET', undefined, 1)).json()).lists).toEqual([]);
  });

  it('requires a session for listing, creating, reading and changing private data', async () => {
    const list = await create();
    for (const [path, method, body] of [
      ['/lists', 'GET'], ['/lists', 'POST', { title: 'x' }], ['/lists/' + list.id, 'GET'],
      ['/lists/' + list.id, 'PUT', { ...list, title: 'x' }], ['/lists/' + list.id, 'DELETE', { version: 1 }],
    ]) expect((await call(path, method, body, null)).status).toBe(401);
    expect(await read(list.id)).toEqual(list);
    expect(await savedCount()).toBe(1);
  });

  it('never permits another account to inspect, edit or delete an owned list', async () => {
    const list = await create();
    await create({ title: 'Other account' }, 1);
    for (const method of ['GET', 'PUT', 'DELETE']) {
      const response = await call('/lists/' + list.id, method, method === 'GET' ? undefined : { ...list, title: 'Stolen' }, 1);
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: 'not_found' });
    }
    expect(await read(list.id)).toEqual(list);
    expect((await (await call('/lists', 'GET', undefined, 1)).json()).lists.map(row => row.title)).toEqual(['Other account']);
  });
});

describe('publication and revisions', () => {
  it('publishes only the chosen display fields, updates the same public id and immediately unpublishes', async () => {
    const draft = await create({ byline: 'Chosen public name' });
    const publish = await call('/lists/' + draft.id.toLowerCase(), 'PUT', { ...draft, published: true });
    expect(publish.status).toBe(200);
    const list = await publish.json();
    expect(list).toMatchObject({ id: draft.id, published: true, version: 2, created_at: draft.created_at });
    const publicResponse = await publicRead(list.id.toLowerCase());
    expect(publicResponse.status).toBe(200);
    expect(publicResponse.headers.get('Cache-Control')).toBe('no-store');
    const publicValue = await publicResponse.json();
    expect(publicValue).toEqual(list);
    expect(Object.keys(publicValue).sort()).toEqual(FIELD_NAMES);
    expect(JSON.stringify(publicValue)).not.toContain('private-');
    // Publication permits only the public read route, not another user's owner route.
    expect((await call('/lists/' + list.id, 'GET', undefined, 1)).status).toBe(404);
    const changed = await (await call('/lists/' + list.id, 'PUT', { ...list, title: 'New name', keys: ['new-core'] })).json();
    expect(await (await publicRead(list.id)).json()).toMatchObject({ id: list.id, title: 'New name', keys: ['new-core'], version: 3 });
    expect((await call('/lists/' + list.id, 'PUT', { ...changed, published: false })).status).toBe(200);
    expect((await publicRead(list.id)).status).toBe(404);
    expect((await publicRead('000000000000')).status).toBe(404);
  });

  it('refuses stale saves and deletes without losing the newer selection', async () => {
    const list = await create();
    const current = await (await call('/lists/' + list.id, 'PUT', { ...list, keys: ['new-selection'] })).json();
    for (const method of ['PUT', 'DELETE']) {
      const response = await call('/lists/' + list.id, method, { ...list, title: 'Stale edit' });
      expect(response.status).toBe(409);
      expect(await response.json()).toEqual({ error: 'conflict', current_version: 2 });
    }
    expect(await read(list.id)).toEqual(current);
    expect((await call('/lists/' + list.id, 'DELETE', { version: current.version })).status).toBe(204);
    expect((await call('/lists/' + list.id)).status).toBe(404);
    expect((await publicRead(list.id)).status).toBe(404);
  });

  it('allows exactly one of two competing saves of the same version', async () => {
    const list = await create();
    const responses = await Promise.all(['one', 'two'].map(title => call('/lists/' + list.id, 'PUT', { ...list, title, keys: [title] })));
    expect(responses.map(response => response.status).sort()).toEqual([200, 409]);
    const winning = await responses.find(response => response.status === 200).json();
    expect(await read(list.id)).toEqual(winning);
    expect(winning.keys).toEqual([winning.title]);
    expect(winning.version).toBe(2);
  });
});

describe('validation', () => {
  it('rejects invalid display fields and row selections without storing anything', async () => {
    for (const [fields, error] of [
      [{ title: '' }, 'bad_title'], [{ title: '   ' }, 'bad_title'], [{ title: 'x'.repeat(101) }, 'bad_title'],
      [{ title: 7 }, 'bad_title'], [{ description: null }, 'bad_description'], [{ description: 'x'.repeat(2001) }, 'bad_description'],
      [{ byline: {} }, 'bad_byline'], [{ byline: 'x'.repeat(81) }, 'bad_byline'],
      [{ keys: 'one' }, 'bad_keys'], [{ keys: [null] }, 'bad_keys'], [{ keys: ['spaces forbidden'] }, 'bad_keys'],
      [{ keys: ['x'.repeat(65)] }, 'bad_keys'], [{ keys: Array(5001).fill('x') }, 'bad_keys'],
    ]) {
      const response = await call('/lists', 'POST', { title: 'Good title', ...fields });
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error });
    }
    expect(await savedCount()).toBe(0);
  });

  it('accepts the maximum selection and field lengths', async () => {
    const keys = Array.from({ length: 5000 }, (_, i) => String(i).padStart(64, 'k'));
    const list = await create({ title: 'x'.repeat(100), description: 'x'.repeat(2000), byline: 'x'.repeat(80), keys });
    expect(list.keys).toEqual(keys);
    expect((await (await call('/lists')).json()).lists[0].count).toBe(5000);
  });

  it('requires full replacement keys, a boolean publication flag and a positive integer version', async () => {
    const list = await create();
    for (const [fields, error] of [
      [{ version: undefined }, 'bad_version'], [{ version: '1' }, 'bad_version'], [{ version: 0 }, 'bad_version'],
      [{ version: 1.5 }, 'bad_version'], [{ version: Number.MAX_SAFE_INTEGER + 1 }, 'bad_version'],
      [{ keys: undefined }, 'bad_keys'], [{ published: undefined }, 'bad_published'], [{ published: 1 }, 'bad_published'],
    ]) {
      const response = await call('/lists/' + list.id, 'PUT', { ...list, ...fields });
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error });
    }
    expect((await call('/lists/' + list.id, 'DELETE', {})).status).toBe(400);
    expect(await read(list.id)).toEqual(list);
  });

  it('caps the actual request body and rejects non-object or malformed JSON', async () => {
    for (const value of ['{', 'null', '[]', '5', '"hello"']) {
      const response = await call('/lists', 'POST', value);
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error: 'bad_json' });
    }
    const huge = await call('/lists', 'POST', { title: 'x', ignored: 'x'.repeat(384 * 1024) });
    expect(huge.status).toBe(413);
    expect(await huge.json()).toEqual({ error: 'too_large' });
    expect(await savedCount()).toBe(0);
  });
});

describe('account cleanup and browser access', () => {
  it('deleting an account removes its drafts and public lists without changing other owners', async () => {
    const draft = await create();
    const published = await create();
    await call('/lists/' + published.id, 'PUT', { ...published, published: true });
    const other = await create({ title: 'Keep this list' }, 1);
    expect((await call('/me', 'DELETE')).status).toBe(400);
    expect(await savedCount()).toBe(3);
    expect((await call('/me', 'DELETE', undefined, 0, { 'X-Confirm': 'delete' })).status).toBe(204);
    expect(await savedCount()).toBe(1);
    expect((await publicRead(published.id)).status).toBe(404);
    expect((await call('/lists/' + draft.id)).status).toBe(401);
    expect(await read(other.id, 1)).toEqual(other);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM sessions WHERE user_id = 1').first('n')).toBe(0);
  });

  it('keeps existing site CORS and never caches owner or public results', async () => {
    const preflight = await call('/lists', 'OPTIONS', undefined, null, { Origin: SITE });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get('Access-Control-Allow-Origin')).toBe(SITE);
    expect(preflight.headers.get('Access-Control-Allow-Methods')).toContain('DELETE');
    expect(preflight.headers.get('Access-Control-Allow-Headers')).toContain('Authorization');
    for (const path of ['/lists', '/public/lists/000000000000']) {
      const response = await call(path, 'GET', undefined, 0, { Origin: SITE });
      expect(response.headers.get('Access-Control-Allow-Origin')).toBe(SITE);
      expect(response.headers.get('Cache-Control')).toBe('no-store');
      const foreign = await call(path, 'GET', undefined, 0, { Origin: 'https://unrelated.example' });
      expect(foreign.headers.get('Access-Control-Allow-Origin')).toBeNull();
    }
  });
});
