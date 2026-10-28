import { env, SELF } from 'cloudflare:test';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import schema from '../schema.sql?raw';
import migration from '../migrations/2026-10-22-list-community.sql?raw';
import titlesMigration from '../migrations/2026-10-27-followed-list-titles.sql?raw';
import trendingMigration from '../migrations/2026-10-28-list-trending.sql?raw';

const API = 'https://api.misterzine.fyi';
const SITE = 'https://misterzine.fyi';
const TOKENS = ['A'.repeat(43), 'B'.repeat(43)];
const FIELD_NAMES = ['id', 'title', 'description', 'byline', 'keys', 'published', 'version', 'created_at', 'updated_at', 'visibility', 'curator', 'follower_count'].sort();
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
const savedCount = async () => env.DB.prepare('SELECT COUNT(*) AS n FROM curated_lists').first('n');
const save = async (list, changes = {}, account = 0) => {
  const response = await call('/lists/' + list.id, 'PUT', { ...list, ...changes }, account);
  expect(response.status).toBe(200);
  return response.json();
};
const directory = async (query = '') => (await call('/public/lists' + query, 'GET', undefined, null)).json();
const collection = async (account = 0) => (await call('/collections', 'GET', undefined, account)).json();

beforeAll(async () => {
  await apply(schema);
  await apply(migration);
  await apply(titlesMigration);
  await apply(titlesMigration);
  await apply(migration); // both schema and the upgrade must be safe to re-run
});
beforeEach(async () => {
  await env.DB.batch(['list_follows', 'public_profiles', 'curated_lists', 'custom_lists', 'feedback', 'sessions', 'favorites', 'users'].map(table => env.DB.prepare('DELETE FROM ' + table)));
  for (let index = 0; index < TOKENS.length; index++) {
    await env.DB.prepare('INSERT INTO users (id, provider, provider_user_id, email) VALUES (?, ?, ?, ?)')
      .bind(index + 1, 'github', 'private-provider-id-' + index, 'private-' + index + '@example.com').run();
    await env.DB.prepare('INSERT INTO sessions (token_hash, user_id) VALUES (?, ?)').bind(await sha256hex(TOKENS[index]), index + 1).run();
  }
  await call('/me/profile', 'PUT', { display_name: 'Matija' });
  await call('/me/profile', 'PUT', { display_name: 'Other curator' }, 1);
});

describe('own lists', () => {
  it('creates a draft with a stable id, exact ordered row keys and chosen account name', async () => {
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
    expect(list).toMatchObject({ published: false, version: 1, byline: 'Matija' });
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
    const publish = await call('/lists/' + draft.id.toLowerCase(), 'PUT', { ...draft, visibility: 'unlisted' });
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
    expect((await call('/lists/' + list.id, 'PUT', { ...changed, visibility: 'private' })).status).toBe(200);
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

  it('requires full replacement keys, a valid visibility and a positive integer version', async () => {
    const list = await create();
    for (const [fields, error] of [
      [{ version: undefined }, 'bad_version'], [{ version: '1' }, 'bad_version'], [{ version: 0 }, 'bad_version'],
      [{ version: 1.5 }, 'bad_version'], [{ version: Number.MAX_SAFE_INTEGER + 1 }, 'bad_version'],
      [{ keys: undefined }, 'bad_keys'], [{ visibility: 'unknown' }, 'bad_visibility'], [{ visibility: 1 }, 'bad_visibility'],
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
    await call('/lists/' + published.id, 'PUT', { ...published, visibility: 'public' });
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

describe('chosen account names', () => {
  it('requires a chosen name before sharing and never substitutes OAuth identity or per-list input', async () => {
    await env.DB.prepare('DELETE FROM public_profiles WHERE user_id = 1').run();
    expect((await (await call('/me')).json()).profile).toBeNull();
    const draft = await create({ byline: 'Ignored per-list name' });
    expect(draft).toMatchObject({ byline: '', curator: { name: '', id: null } });
    for (const visibility of ['unlisted', 'public']) {
      const response = await call('/lists/' + draft.id, 'PUT', { ...draft, visibility });
      expect(response.status).toBe(409);
      expect(await response.json()).toEqual({ error: 'profile_required' });
    }
    expect(await read(draft.id)).toEqual(draft);
    const profile = await (await call('/me/profile', 'PUT', { display_name: '  Chosen name  ' })).json();
    expect(profile).toEqual({ id: expect.stringMatching(/^[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{12}$/), display_name: 'Chosen name' });
    const shared = await save(draft, { visibility: 'unlisted' });
    expect(shared.curator).toEqual({ name: 'Chosen name', id: null });
    expect(shared.byline).toBe('Chosen name');
    expect((await (await call('/me')).json()).profile).toEqual(profile);
  });

  it('keeps a stable profile id across renames, allows duplicate names and does not change list dates or versions', async () => {
    const draft = await create();
    const shared = await save(await create(), { visibility: 'public' });
    const before = (await (await call('/me')).json()).profile;
    const response = await call('/me/profile', 'PUT', { display_name: 'Other curator' });
    expect(response.status).toBe(200);
    const profile = await response.json();
    expect(profile).toEqual({ id: before.id, display_name: 'Other curator' });
    const other = (await (await call('/me', 'GET', undefined, 1)).json()).profile;
    expect(other.display_name).toBe(profile.display_name);
    expect(other.id).not.toBe(profile.id);
    for (const original of [draft, shared]) {
      const current = await read(original.id);
      expect(current).toMatchObject({ byline: profile.display_name, version: original.version, updated_at: original.updated_at });
      expect(current.curator.id).toBe(original.visibility === 'public' ? profile.id : null);
    }
    expect((await directory('?q=Other%20curator')).lists.map(row => row.id)).toEqual([shared.id]);
  });

  it('validates names, caps profile bodies and refuses anonymous changes', async () => {
    const before = (await (await call('/me')).json()).profile;
    for (const display_name of ['', ' ', null, 5, 'x'.repeat(81)]) {
      const response = await call('/me/profile', 'PUT', { display_name });
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error: 'bad_display_name' });
    }
    expect((await call('/me/profile', 'PUT', { display_name: 'x' }, null)).status).toBe(401);
    expect((await call('/me/profile', 'PUT', { display_name: 'x', ignored: 'x'.repeat(4096) })).status).toBe(413);
    expect((await (await call('/me')).json()).profile).toEqual(before);
    expect((await call('/me/profile', 'PUT', { display_name: 'x'.repeat(80) })).status).toBe(200);
  });
});

describe('public discovery and curator privacy', () => {
  it('exposes public lists only in directory/profile and never leaks private or unlisted ids through their curator', async () => {
    const privateList = await create({ title: 'Secret game list' });
    const unlisted = await save(await create({ title: 'Secret link list' }), { visibility: 'unlisted' });
    const publicList = await save(await create({ title: 'Visible list' }), { visibility: 'public' });
    const profile = (await (await call('/me')).json()).profile;
    expect((await directory()).lists.map(row => row.id)).toEqual([publicList.id]);
    expect((await directory('?q=Secret')).total).toBe(0);
    const curator = await (await call('/public/curators/' + profile.id.toLowerCase(), 'GET', undefined, null)).json();
    expect(curator.profile).toEqual(profile);
    expect(curator.lists.map(row => row.id)).toEqual([publicList.id]);
    expect(JSON.stringify(curator)).not.toContain(privateList.id);
    expect(JSON.stringify(curator)).not.toContain(unlisted.id);
    expect((await (await publicRead(unlisted.id)).json()).curator).toEqual({ name: profile.display_name, id: null });
    expect((await publicRead(privateList.id)).status).toBe(404);
    await save(publicList, { visibility: 'unlisted' });
    expect(await directory()).toEqual({ lists: [], total: 0, has_more: false });
    expect((await call('/public/curators/' + profile.id, 'GET', undefined, null)).status).toBe(404);
  });

  it('uses literal search and deterministic bounded pagination for all directory sorts', async () => {
    const a = await save(await create({ title: 'Alpha', description: 'Mahjong favourites' }), { visibility: 'public' });
    const b = await save(await create({ title: 'Beta 100%' }), { visibility: 'public' });
    const c = await save(await create({ title: 'Gamma' }), { visibility: 'public' });
    // Equal timestamps must still produce deterministic pages.
    await env.DB.prepare("UPDATE curated_lists SET created_at = '2020-01-01T00:00:00Z', updated_at = '2020-01-02T00:00:00Z'").run();
    const ids = [a.id, b.id, c.id].sort();
    for (const sort of ['updated', 'created', 'followers', 'trending']) {
      const first = await directory('?sort=' + sort + '&limit=2');
      const second = await directory('?sort=' + sort + '&offset=2&limit=2');
      expect(first).toMatchObject({ total: 3, has_more: true });
      expect(second).toMatchObject({ total: 3, has_more: false });
      expect([...first.lists, ...second.lists].map(row => row.id)).toEqual(ids);
      expect(first.lists[0]).not.toHaveProperty('keys');
      expect(first.lists[0]).toHaveProperty('count', 2);
    }
    expect((await directory('?q=mahjong')).lists.map(row => row.id)).toEqual([a.id]);
    expect((await directory('?q=matija')).total).toBe(3);
    expect((await directory('?q=%25')).lists.map(row => row.id)).toEqual([b.id]);
    expect((await directory('?q=_')).total).toBe(0);
    expect((await call('/following/' + c.id, 'PUT', undefined, 1)).status).toBe(204);
    expect((await directory('?sort=followers')).lists[0]).toMatchObject({ id: c.id, follower_count: 1 });
    for (const query of ['?sort=bogus', '?offset=-1', '?offset=10001', '?offset=x', '?limit=0', '?limit=101', '?limit=1.5', '?q=' + 'x'.repeat(201)])
      expect((await call('/public/lists' + query, 'GET', undefined, null)).status).toBe(400);
    expect(await directory('?offset=10000')).toEqual({ lists: [], total: 3, has_more: false });
  });
});

describe('trending lists', () => {
  it('uses a smooth seven-day half-life, independent of list age and edits, with normal privacy filtering', async () => {
    const fresh = await save(await create({title:'Fresh interest'}), {visibility:'public'});
    const older = await save(await create({title:'Older interest'}), {visibility:'public'});
    const empty = await save(await create({title:'No follows'}), {visibility:'public'});
    const privateList = await create();
    const unlisted = await save(await create(), {visibility:'unlisted'});
    await env.DB.prepare("INSERT INTO users(id,provider,provider_user_id) VALUES (3,'github','third')").run();
    // One new follow beats two follows just over a week old.
    for (const [id, user, age] of [[fresh.id,2,0],[older.id,2,8],[older.id,3,8],[privateList.id,2,0],[unlisted.id,2,0]]) {
      await env.DB.prepare("INSERT INTO list_follows(user_id,list_id,created_at) VALUES (?,?,datetime('now',?))")
        .bind(user,id,'-' + age + ' days').run();
    }
    await apply(trendingMigration);
    await apply(trendingMigration);
    await env.DB.prepare("UPDATE curated_lists SET created_at='2000-01-01',updated_at='2000-01-01' WHERE id=?").bind(fresh.id).run();
    expect((await directory('?sort=trending')).lists.map(l=>l.id)).toEqual([fresh.id,older.id,empty.id]);
    // Two follows just under a week old beat one new follow: no weekly cutoff.
    await env.DB.prepare("UPDATE list_follow_history SET first_followed_at=datetime('now','-6 days') WHERE list_id=?").bind(older.id).run();
    expect((await directory('?sort=trending')).lists.map(l=>l.id)).toEqual([older.id,fresh.id,empty.id]);
    const first=await directory('?sort=trending&limit=1');
    const next=await directory('?sort=trending&limit=1&offset=1');
    expect(first).toMatchObject({total:3,has_more:true});
    expect(next.lists[0].id).toBe(fresh.id);
    expect((await directory('?sort=trending&q=Fresh')).lists.map(l=>l.id)).toEqual([fresh.id]);
    expect(first.lists[0]).not.toHaveProperty('first_followed_at');
    await env.DB.prepare("INSERT INTO list_moderation(list_id,hidden,reason,moderated_by) VALUES (?,1,'test',2)").bind(older.id).run();
    expect((await directory('?sort=trending')).lists.map(l=>l.id)).toEqual([fresh.id,empty.id]);
    await env.DB.prepare("UPDATE users SET provider='google',email='matija.erceg@gmail.com' WHERE id=2").run();
    const hidden=await call('/admin/lists?sort=trending&hidden=1&shared=1','GET',undefined,1);
    expect(hidden.status).toBe(200);
    expect((await hidden.json()).lists.map(l=>l.id)).toEqual([older.id]);
  });

  it('keeps the first date through repeated follows and pinning, counts only active follows, and deletes history with its account or list', async () => {
    const a=await save(await create(),{visibility:'public'});
    const b=await save(await create(),{visibility:'public'});
    expect((await call('/following/'+a.id,'PUT',undefined,1)).status).toBe(204);
    await env.DB.prepare("UPDATE list_follow_history SET first_followed_at=datetime('now','-28 days') WHERE list_id=?").bind(a.id).run();
    const firstDate=()=>env.DB.prepare('SELECT first_followed_at FROM list_follow_history WHERE list_id=?').bind(a.id).first('first_followed_at');
    const originalDate=await firstDate();
    await call('/following/'+a.id,'PUT',undefined,1);
    await call('/following/'+a.id,'DELETE',undefined,1);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_follows WHERE list_id=?').bind(a.id).first('n')).toBe(0);
    expect(await firstDate()).toBe(originalDate);
    await call('/following/'+a.id,'PUT',undefined,1);
    expect(await firstDate()).toBe(originalDate);
    await call('/following/'+a.id,'DELETE',undefined,1);
    await call('/pins/'+a.id,'PUT',undefined,1);
    await call('/pins/'+b.id,'PUT',undefined,1);
    await apply(trendingMigration);
    expect(await firstDate()).toBe(originalDate);
    expect((await directory('?sort=trending')).lists[0].id).toBe(b.id);
    await call('/following/'+b.id,'DELETE',undefined,1);
    expect((await directory('?sort=trending')).lists[0].id).toBe(a.id);
    await env.DB.prepare('DELETE FROM curated_lists WHERE id=?').bind(a.id).run();
    expect(await firstDate()).toBeNull();
    await env.DB.prepare('DELETE FROM users WHERE id=2').run();
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_follow_history').first('n')).toBe(0);
  });
});

describe('following lists', () => {
  it('counts concurrent follows once, hides follower identity and supports idempotent unfollow', async () => {
    const list = await save(await create(), { visibility: 'unlisted' });
    const responses = await Promise.all(Array.from({ length: 4 }, () => call('/following/' + list.id.toLowerCase(), 'PUT', undefined, 1)));
    expect(responses.map(response => response.status)).toEqual([204, 204, 204, 204]);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_follows').first('n')).toBe(1);
    const publicValue = await (await publicRead(list.id)).json();
    expect(publicValue.follower_count).toBe(1);
    expect(Object.keys(publicValue).sort()).toEqual(FIELD_NAMES);
    expect(JSON.stringify(publicValue)).not.toContain('private-');
    const followed = (await collection(1)).following;
    expect(followed).toHaveLength(1);
    expect(followed[0]).toMatchObject({ id: list.id, follower_count: 1, count: 2 });
    expect((await collection()).following).toEqual([]);
    expect((await call('/following/' + list.id, 'PUT')).status).toBe(400);
    expect((await call('/following/' + list.id, 'PUT', undefined, null)).status).toBe(401);
    expect((await call('/collections', 'GET', undefined, null)).status).toBe(401);
    for (let i = 0; i < 2; i++) expect((await call('/following/' + list.id, 'DELETE', undefined, 1)).status).toBe(204);
    expect((await read(list.id)).follower_count).toBe(0);
    expect((await collection(1)).following).toEqual([]);
  });

  it('retains only a remembered title and unavailable id after withdrawal or deletion and resumes after sharing again', async () => {
    let list = await save(await create({ title: 'A private title later', description: 'Secret after withdrawal' }), { visibility: 'public' });
    await call('/following/' + list.id, 'PUT', undefined, 1);
    list = await save(list, { visibility: 'private' });
    expect((await collection(1)).following).toEqual([{ id: list.id, title: list.title, unavailable: true }]);
    expect((await call('/following/' + list.id, 'PUT', undefined, 1)).status).toBe(404);
    expect((await publicRead(list.id)).status).toBe(404);
    list = await save(list, { visibility: 'unlisted' });
    expect((await collection(1)).following[0]).toMatchObject({ id: list.id, title: list.title, follower_count: 1 });
    expect((await call('/lists/' + list.id, 'DELETE', { version: list.version })).status).toBe(204);
    expect((await collection(1)).following).toEqual([{ id: list.id, title: list.title, unavailable: true }]);
    expect((await call('/following/' + list.id, 'DELETE', undefined, 1)).status).toBe(204);
    expect((await collection(1)).following).toEqual([]);
    expect((await call('/following/000000000000', 'PUT', undefined, 1)).status).toBe(404);
  });

  it('remembers the last accessible title without revealing later private edits', async () => {
    let list = await save(await create({ title: 'Remember this title' }), { visibility: 'public' });
    await call('/following/' + list.id, 'PUT', undefined, 1);
    await collection(1);
    list = await save(list, { visibility: 'private', title: 'Secret renamed title', keys: ['private_game'], description: 'Private notes' });
    expect((await collection(1)).following).toEqual([{ id: list.id, title: 'Remember this title', unavailable: true }]);
    await call('/lists/' + list.id, 'DELETE', { version: list.version });
    expect((await collection(1)).following).toEqual([{ id: list.id, title: 'Remember this title', unavailable: true }]);
    await call('/following/' + list.id, 'DELETE', undefined, 1);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_follow_titles').first('n')).toBe(0);
  });

  it('never exposes private content when a follow races withdrawal', async () => {
    const list = await save(await create(), { visibility: 'public' });
    const [follow, withdraw] = await Promise.all([
      call('/following/' + list.id, 'PUT', undefined, 1),
      call('/lists/' + list.id, 'PUT', { ...list, visibility: 'private' }),
    ]);
    expect([204, 404]).toContain(follow.status);
    expect(withdraw.status).toBe(200);
    const following = (await collection(1)).following;
    expect(following.length).toBeLessThanOrEqual(1);
    if (following.length) expect(following).toEqual([{ id: list.id, title: list.title, unavailable: true }]);
  });

  it('account deletion removes its name and own follows while preserving other followers as unavailable', async () => {
    const mine = await save(await create(), { visibility: 'public' });
    const other = await save(await create({ title: 'Other list' }, 1), { visibility: 'public' }, 1);
    await call('/following/' + other.id, 'PUT');
    await call('/following/' + mine.id, 'PUT', undefined, 1);
    expect((await call('/me', 'DELETE', undefined, 0, { 'X-Confirm': 'delete' })).status).toBe(204);
    expect((await collection(1)).following).toEqual([{ id: mine.id, title: mine.title, unavailable: true }]);
    expect((await read(other.id, 1)).follower_count).toBe(0);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM public_profiles WHERE user_id = 1').first('n')).toBe(0);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_follows WHERE user_id = 1').first('n')).toBe(0);
    expect((await call('/public/curators/' + mine.curator.id, 'GET', undefined, null)).status).toBe(404);
  });
});

describe('revision and migration semantics', () => {
  it('no-op saves preserve date/version while visibility only changes version and content changes both', async () => {
    let list = await create();
    const oldDate = '2020-01-01T00:00:00.000Z';
    await env.DB.prepare('UPDATE curated_lists SET updated_at = ? WHERE id = ?').bind(oldDate, list.id).run();
    list = await read(list.id);
    expect(await save(list, { byline: 'Ignored', title: ' ' + list.title + ' ' })).toEqual(list);
    const publicList = await save(list, { visibility: 'public' });
    expect(publicList).toMatchObject({ updated_at: oldDate, version: 2 });
    expect(await save(publicList)).toEqual(publicList);
    // A stale no-op must still reject; it cannot reset the visibility/date.
    const stale = await call('/lists/' + list.id, 'PUT', { ...publicList, version: 1 });
    expect(stale.status).toBe(409);
    const reordered = await save(publicList, { keys: [...publicList.keys].reverse() });
    expect(reordered.version).toBe(3);
    expect(reordered.updated_at).not.toBe(oldDate);
    expect(reordered.keys).toEqual([...publicList.keys].reverse());
  });

  it('maps legacy published=true to unlisted only when visibility is absent', async () => {
    const draft = await create();
    const { visibility, ...legacy } = draft;
    const shared = await save(legacy, { published: true });
    expect(shared.visibility).toBe('unlisted');
    expect(shared.published).toBe(true);
    expect((await directory()).total).toBe(0);
    expect((await save(shared, { published: true, visibility: 'private' })).published).toBe(false);
  });

  it('moves old shared links to unlisted without guessing profiles, and reruns never overwrite or resurrect', async () => {
    await env.DB.prepare('DELETE FROM public_profiles WHERE user_id = 1').run();
    await env.DB.prepare('INSERT INTO custom_lists (id, user_id, title, byline, published, keys_json) VALUES (?, 1, ?, ?, 1, ?)')
      .bind('AAAAAAAAAAAA', 'Legacy list', 'Legacy chosen byline', '["galaga"]').run();
    await apply(migration);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM custom_lists').first('n')).toBe(0);
    const list = await read('AAAAAAAAAAAA');
    expect(list).toMatchObject({ title: 'Legacy list', byline: 'Legacy chosen byline', visibility: 'unlisted', curator: { name: 'Legacy chosen byline', id: null } });
    expect((await publicRead(list.id)).status).toBe(200);
    expect((await (await call('/me')).json()).profile).toBeNull();
    expect((await directory()).total).toBe(0);
    await call('/me/profile', 'PUT', { display_name: 'Account name now' });
    const changed = await save(list, { title: 'Edited after migration' });
    await apply(migration);
    expect(await read(list.id)).toEqual(changed);
    await call('/lists/' + list.id, 'DELETE', { version: changed.version });
    await apply(migration);
    expect((await call('/lists/' + list.id)).status).toBe(404);
  });
});

 describe('pinned collection tabs', () => {
  it('pins own private lists and automatically follows accessible lists; unpin preserves follow', async () => {
    const mine = await create();
    expect((await call('/pins/' + mine.id, 'PUT')).status).toBe(204);
    expect((await collection()).pins).toEqual([{id:mine.id,title:mine.title}]);
    expect((await call('/pins/' + mine.id, 'PUT', undefined, 1)).status).toBe(404);
    const shared = await save(mine, {visibility:'unlisted'});
    expect((await call('/pins/' + mine.id, 'PUT', undefined, 1)).status).toBe(204);
    expect((await collection(1)).following[0].id).toBe(mine.id);
    await call('/pins/' + mine.id, 'DELETE', undefined, 1);
    expect((await collection(1)).pins).toEqual([]);
    expect((await collection(1)).following[0].id).toBe(mine.id);
    await call('/pins/' + mine.id, 'PUT', undefined, 1);
    await save(shared, {title:'Secret new title',visibility:'private'});
    const hidden = await collection(1);
    expect(hidden.pins).toEqual([{id:mine.id,title:mine.title}]);
    expect(hidden.following[0].unavailable).toBe(true);
    expect((await call('/pins/' + mine.id, 'DELETE', undefined, 1)).status).toBe(204);
  });
 });


describe('list moderation', () => {
  const admin = async () => env.DB.prepare("UPDATE users SET provider='google',email='matija.erceg@gmail.com' WHERE id=2").run();
  const moderate = (list, hidden=true, extra={}) => call('/admin/lists/'+list.id,'PUT',{hidden,reason:'Review needed',version:list.version,...extra},1);
  it('restricts reads and writes to the verified Google identity, including forged profile email', async () => {
    const list=await create();
    expect((await call('/admin/lists','GET',undefined,null)).status).toBe(401);
    await env.DB.prepare("UPDATE users SET email='matija.erceg@gmail.com' WHERE id=2").run();
    expect((await call('/admin/lists','GET',undefined,1)).status).toBe(403);
    expect((await moderate(list)).status).toBe(403);
    expect((await (await call('/me','GET',undefined,1)).json()).list_admin).toBe(false);
    await admin();
    expect((await (await call('/me','GET',undefined,1)).json()).list_admin).toBe(true);
    expect((await call('/admin/lists/'+list.id,'GET',undefined,1)).status).toBe(200);
    await env.DB.prepare("UPDATE users SET email=NULL WHERE id=2").run();
    expect((await moderate(list)).status).toBe(403);
  });
  it('hides shared access everywhere, keeps owner editing, and restores the current visibility', async () => {
    let list=await save(await create(),{visibility:'public'});
    await call('/pins/'+list.id,'PUT',undefined,1);
    await admin();
    expect((await moderate(list)).status).toBe(204);
    expect((await publicRead(list.id)).status).toBe(404);
    expect((await directory()).lists).toEqual([]);
    expect((await call('/public/curators/'+list.curator.id,'GET',undefined,null)).status).toBe(404);
    expect((await call('/following/'+list.id,'PUT',undefined,1)).status).toBe(404);
    expect((await call('/pins/'+list.id,'PUT',undefined,1)).status).toBe(404);
    const c=await collection(1);
    expect(c.following).toEqual([{id:list.id,title:'Unavailable list',unavailable:true}]);
    expect(c.pins[0].title).toBe('Unavailable list');
    expect((await read(list.id)).moderation_hidden).toBe(true);
    list=await save(list,{title:'Edited while hidden',visibility:'unlisted'});
    expect(list.moderation_hidden).toBe(true);
    expect((await publicRead(list.id)).status).toBe(404);
    expect((await (await call('/admin/lists?hidden=1','GET',undefined,1)).json()).lists).toHaveLength(1);
    expect((await moderate(list,false)).status).toBe(204);
    expect((await publicRead(list.id)).status).toBe(200);
    expect((await directory()).lists).toEqual([]);
    expect((await collection(1)).following[0].title).toBe('Edited while hidden');
  });
  it('requires a reason and current content revision; private lists remain private on restore', async () => {
    const list=await create(); await admin();
    expect((await moderate(list,true,{reason:''})).status).toBe(400);
    expect((await moderate(list,true,{version:99})).status).toBe(409);
    expect((await moderate(list)).status).toBe(204);
    expect((await moderate(list,false)).status).toBe(204);
    expect((await publicRead(list.id)).status).toBe(404);
    expect((await call('/admin/lists?offset=-1','GET',undefined,1)).status).toBe(400);
    await call('/lists/'+list.id,'DELETE',{version:list.version});
    expect((await moderate(list)).status).toBe(404);
    expect(await env.DB.prepare('SELECT COUNT(*) AS n FROM list_moderation').first('n')).toBe(0);
  });
});


it('caps owned lists atomically and still permits editing and deletion at the cap',async()=>{
  const list=await create();
  await env.DB.prepare("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<198) INSERT INTO curated_lists(id,user_id,title) SELECT printf('%012d',x),1,'Quota fixture' FROM n").run();
  const results=await Promise.all([call('/lists','POST',{title:'Last slot'}),call('/lists','POST',{title:'Overflow'})]);
  expect(results.map(r=>r.status).sort()).toEqual([201,409]);expect(await savedCount()).toBe(200);
  expect(await (await call('/lists','POST',{title:'Overflow'})).json()).toEqual({error:'list_limit'});
  await save(list,{title:'Still editable'});
  const current=await read(list.id);expect((await call('/lists/'+list.id,'DELETE',{version:current.version})).status).toBe(204);
  expect((await call('/lists','POST',{title:'Slot freed'})).status).toBe(201);
});


it('paginates a thousand-list dataset without exposing private, unlisted or hidden entries',async()=>{
  await env.DB.prepare("INSERT INTO users(id,provider,provider_user_id) VALUES (3,'github','scale3'),(4,'github','scale4'),(5,'github','scale5'),(6,'github','scale6')").run();
  await env.DB.prepare("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) INSERT INTO curated_lists(id,user_id,title,visibility) SELECT printf('%012d',x),1+((x-1)/200),printf('Scale %04d',x),CASE WHEN x%4=0 THEN 'private' WHEN x%4=1 THEN 'unlisted' ELSE 'public' END FROM n").run();
  await env.DB.prepare("INSERT INTO list_moderation(list_id,hidden,reason,moderated_by) SELECT id,1,'Scale hidden',1 FROM curated_lists WHERE CAST(id AS INTEGER)%10=2").run();
  const expected=(await env.DB.prepare("SELECT id FROM curated_lists l WHERE visibility='public' AND NOT EXISTS(SELECT 1 FROM list_moderation m WHERE m.list_id=l.id AND hidden=1) ORDER BY updated_at DESC,id").all()).results.map(r=>r.id);
  const ids=[];let page;
  do {page=await directory('?q=Scale&limit=100&offset='+ids.length);expect(page.total).toBe(expected.length);ids.push(...page.lists.map(r=>r.id));} while(page.has_more);
  expect(ids).toEqual(expected);expect(new Set(ids).size).toBe(ids.length);
  expect((await directory('?q=Scale%200002')).lists).toEqual([]);
  expect((await publicRead('000000000002')).status).toBe(404);
});
