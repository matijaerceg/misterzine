// Explicit public names are separate from OAuth identity. Unlisted links reveal
// no profile id or other lists. Ordered selections remain atomic single rows.
import { readCapped } from './reports.js';

const KEY_RE = /^[A-Za-z0-9_-]{1,64}$/;
const ID_RE = /^[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{12}$/;
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const BODY_MAX = 384 * 1024;
const VISIBILITY = ['private', 'unlisted', 'public'];
const META = 'l.id, l.title, l.description, l.byline, l.visibility, l.version, l.created_at, l.updated_at, ' +
  'p.id AS curator_id, p.display_name AS curator_name, ' +
  '(SELECT COUNT(*) FROM list_follows f WHERE f.list_id = l.id) AS follower_count';
const FROM = ' FROM curated_lists l LEFT JOIN public_profiles p ON p.user_id = l.user_id';
const SUMMARY = 'SELECT ' + META + ', json_array_length(l.keys_json) AS count' + FROM;
const FULL = 'SELECT ' + META + ', l.keys_json' + FROM;

export async function getProfile(env, userId) {
  return env.DB.prepare('SELECT id, display_name FROM public_profiles WHERE user_id = ?').bind(userId).first();
}
export async function updateProfile(request, env, user) {
  const parsed = await body(request, 4096);
  if (parsed.error) return json({ error: parsed.error }, parsed.status);
  const name = parsed.value.display_name;
  if (typeof name !== 'string' || !name.trim() || name.trim().length > 80) return json({ error: 'bad_display_name' }, 400);
  for (let attempt = 0; attempt < 5; attempt++) {
    const row = await env.DB.prepare(
      'INSERT INTO public_profiles (user_id, id, display_name) VALUES (?, ?, ?) ' +
      'ON CONFLICT(user_id) DO UPDATE SET display_name = excluded.display_name ' +
      'ON CONFLICT(id) DO NOTHING RETURNING id, display_name'
    ).bind(user.id, newId(), name.trim()).first();
    if (row) return json(row);
  }
  return json({ error: 'unavailable' }, 503);
}
export async function publicLists(env, path, method, url) {
  if (method !== 'GET') return json({ error: 'not_found' }, 404);
  if (path === '/public/lists') return directory(env, url.searchParams);
  let match = path.match(/^\/public\/curators\/([^/]+)$/);
  if (match) {
    const id = normalizeId(match[1]);
    if (!id) return json({ error: 'not_found' }, 404);
    const [profile, items] = await env.DB.batch([
      env.DB.prepare('SELECT id, display_name FROM public_profiles WHERE id = ?').bind(id),
      env.DB.prepare(SUMMARY + " WHERE p.id = ? AND l.visibility = 'public' ORDER BY l.updated_at DESC, l.id").bind(id),
    ]);
    if (!profile.results.length || !items.results.length) return json({ error: 'not_found' }, 404);
    return json({ profile: profile.results[0], lists: items.results.map(present) });
  }
  match = path.match(/^\/public\/lists\/([^/]+)$/);
  const id = match && normalizeId(match[1]);
  if (!id) return json({ error: 'not_found' }, 404);
  const row = await env.DB.prepare(FULL + " WHERE l.id = ? AND l.visibility IN ('unlisted', 'public')").bind(id).first();
  return row ? json(present(row)) : json({ error: 'not_found' }, 404);
}
async function directory(env, params) {
  const query = (params.get('q') || '').trim(), sort = params.get('sort') || 'updated';
  const number = (key, fallback) => params.has(key) && /^\d+$/.test(params.get(key)) ? Number(params.get(key)) : params.has(key) ? NaN : fallback;
  const offset = number('offset', 0), limit = number('limit', 24);
  if (query.length > 200 || !['updated', 'created', 'followers'].includes(sort) ||
      !Number.isSafeInteger(offset) || offset < 0 || offset > 10000 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100)
    return json({ error: 'bad_query' }, 400);
  const where = " WHERE l.visibility = 'public'" + (query
    ? " AND instr(lower(l.title || char(10) || l.description || char(10) || COALESCE(p.display_name, l.byline)), lower(?)) > 0" : '');
  const bindings = query ? [query] : [];
  const order = { updated: 'l.updated_at DESC, l.id', created: 'l.created_at DESC, l.id', followers: 'follower_count DESC, l.updated_at DESC, l.id' }[sort];
  const [count, page] = await env.DB.batch([
    env.DB.prepare('SELECT COUNT(*) AS total' + FROM + where).bind(...bindings),
    env.DB.prepare(SUMMARY + where + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?').bind(...bindings, limit, offset),
  ]);
  const total = count.results[0].total;
  return json({ lists: page.results.map(present), total, has_more: offset + page.results.length < total });
}
async function owned(env, userId) {
  return (await env.DB.prepare(SUMMARY + ' WHERE l.user_id = ? ORDER BY l.updated_at DESC, l.id').bind(userId).all()).results.map(present);
}
export async function collections(env, user) {
  const mine = await owned(env, user.id);
  // Remember accessible titles, but never retain keys or private content.
  await env.DB.prepare("INSERT INTO list_follow_titles (user_id, list_id, title) SELECT f.user_id, f.list_id, l.title FROM list_follows f JOIN curated_lists l ON l.id = f.list_id WHERE f.user_id = ? AND l.visibility IN ('public', 'unlisted') ON CONFLICT(user_id, list_id) DO UPDATE SET title = excluded.title").bind(user.id).run();
  const { results } = await env.DB.prepare('SELECT ' + META + ', json_array_length(l.keys_json) AS count, f.list_id AS followed_id, t.title AS remembered_title ' +
    "FROM list_follows f LEFT JOIN curated_lists l ON l.id = f.list_id AND l.visibility IN ('unlisted', 'public') " +
    'LEFT JOIN list_follow_titles t ON t.user_id = f.user_id AND t.list_id = f.list_id LEFT JOIN public_profiles p ON p.user_id = l.user_id WHERE f.user_id = ? ORDER BY f.created_at DESC, f.list_id').bind(user.id).all();
  return json({ owned: mine, following: results.map(row => row.id ? present(row) : { id: row.followed_id, title: row.remembered_title || 'Unavailable list', unavailable: true }) });
}
export async function following(env, method, path, user) {
  const match = path.match(/^\/following\/([^/]+)$/), id = match && normalizeId(match[1]);
  if (!id || !['PUT', 'DELETE'].includes(method)) return json({ error: 'not_found' }, 404);
  if (method === 'DELETE') {
    await env.DB.prepare('DELETE FROM list_follows WHERE user_id = ? AND list_id = ?').bind(user.id, id).run();
    return empty();
  }
  // Unique (user_id,list_id) and a transaction prevent follow/access races.
  const [, check] = await env.DB.batch([
    env.DB.prepare('INSERT INTO list_follows (user_id, list_id) SELECT ?, id FROM curated_lists ' +
      "WHERE id = ? AND user_id <> ? AND visibility IN ('unlisted', 'public') ON CONFLICT(user_id, list_id) DO NOTHING").bind(user.id, id, user.id),
    env.DB.prepare('SELECT user_id, visibility FROM curated_lists WHERE id = ?').bind(id),
    env.DB.prepare("INSERT OR IGNORE INTO list_follow_titles (user_id, list_id, title) SELECT f.user_id, f.list_id, l.title FROM list_follows f JOIN curated_lists l ON l.id=f.list_id WHERE f.user_id=? AND f.list_id=? AND l.visibility IN ('public','unlisted')").bind(user.id, id),
  ]);
  const row = check.results[0];
  if (row && row.user_id === user.id) return json({ error: 'own_list' }, 400);
  return row && row.visibility !== 'private' ? empty() : json({ error: 'not_found' }, 404);
}
export async function lists(request, env, method, path, user) {
  if (path === '/lists' && method === 'GET') return json({ lists: await owned(env, user.id) });
  if (path === '/lists' && method === 'POST') {
    const parsed = await body(request);
    if (parsed.error) return json({ error: parsed.error }, parsed.status);
    const value = validate(parsed.value, false);
    if (value.error) return json({ error: value.error }, 400);
    for (let attempt = 0; attempt < 5; attempt++) {
      const id = newId();
      const row = await env.DB.prepare('INSERT INTO curated_lists (id, user_id, title, description, keys_json) ' +
        'SELECT ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM list_follows WHERE list_id = ?) ' +
        'ON CONFLICT(id) DO NOTHING RETURNING *'
      ).bind(id, user.id, value.title, value.description, JSON.stringify(value.keys), id).first();
      if (row) return json(await enrich(env, row), 201);
    }
    return json({ error: 'unavailable' }, 503);
  }
  const match = path.match(/^\/lists\/([^/]+)$/), id = match && normalizeId(match[1]);
  if (!id || !['GET', 'PUT', 'DELETE'].includes(method)) return json({ error: 'not_found' }, 404);
  if (method === 'GET') {
    const row = await env.DB.prepare(FULL + ' WHERE l.id = ? AND l.user_id = ?').bind(id, user.id).first();
    return row ? json(present(row)) : json({ error: 'not_found' }, 404);
  }
  const parsed = await body(request);
  if (parsed.error) return json({ error: parsed.error }, parsed.status);
  if (!Number.isSafeInteger(parsed.value.version) || parsed.value.version < 1) return json({ error: 'bad_version' }, 400);
  if (method === 'DELETE') {
    const row = await env.DB.prepare('DELETE FROM curated_lists WHERE id = ? AND user_id = ? AND version = ? RETURNING id')
      .bind(id, user.id, parsed.value.version).first();
    if (row) return empty();
  } else {
    const value = validate(parsed.value, true);
    if (value.error) return json({ error: value.error }, 400);
    if (value.visibility !== 'private' && !(await getProfile(env, user.id))) {
      const current = await env.DB.prepare('SELECT version FROM curated_lists WHERE id = ? AND user_id = ?').bind(id, user.id).first();
      if (!current) return json({ error: 'not_found' }, 404);
      if (current.version !== value.version) return json({ error: 'conflict', current_version: current.version }, 409);
      return json({ error: 'profile_required' }, 409);
    }
    // Even no-ops check revision atomically. Visibility changes advance revision
    // but only actual content changes advance the date used by the directory.
    const contentChanged = '(title <> ?1 OR description <> ?2 OR keys_json <> ?3)';
    const row = await env.DB.prepare('UPDATE curated_lists SET title = ?1, description = ?2, keys_json = ?3, visibility = ?4, ' +
      'version = version + CASE WHEN ' + contentChanged + ' OR visibility <> ?4 THEN 1 ELSE 0 END, ' +
      'updated_at = CASE WHEN ' + contentChanged + " THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') ELSE updated_at END " +
      'WHERE id = ?5 AND user_id = ?6 AND version = ?7 RETURNING *'
    ).bind(value.title, value.description, JSON.stringify(value.keys), value.visibility, id, user.id, value.version).first();
    if (row) return json(await enrich(env, row));
  }
  const current = await env.DB.prepare('SELECT version FROM curated_lists WHERE id = ? AND user_id = ?').bind(id, user.id).first();
  return current ? json({ error: 'conflict', current_version: current.version }, 409) : json({ error: 'not_found' }, 404);
}
function validate(input, updating) {
  if (typeof input.title !== 'string' || !input.title.trim() || input.title.trim().length > 100) return { error: 'bad_title' };
  const description = input.description === undefined ? '' : input.description;
  if (typeof description !== 'string' || description.length > 2000) return { error: 'bad_description' };
  const keys = !updating && input.keys === undefined ? [] : input.keys;
  if (!Array.isArray(keys) || keys.length > 5000 || !keys.every(key => typeof key === 'string' && KEY_RE.test(key))) return { error: 'bad_keys' };
  const visibility = input.visibility === undefined && typeof input.published === 'boolean'
    ? (input.published ? 'unlisted' : 'private') : input.visibility;
  if (updating && !VISIBILITY.includes(visibility)) return { error: 'bad_visibility' };
  // Old byline inputs are ignored. Only /me/profile changes a curator name.
  return { title: input.title.trim(), description: description.trim(), keys: [...new Set(keys)], visibility, version: input.version };
}
async function body(request, max = BODY_MAX) {
  if (Number(request.headers.get('Content-Length')) > max) return { error: 'too_large', status: 413 };
  const bytes = await readCapped(request, max);
  if (!bytes) return { error: 'too_large', status: 413 };
  let value;
  try { value = JSON.parse(new TextDecoder().decode(bytes)); } catch (e) {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { error: 'bad_json', status: 400 };
  return { value };
}
async function enrich(env, row) {
  const meta = await env.DB.prepare('SELECT (SELECT id FROM public_profiles WHERE user_id = ?1) AS curator_id, ' +
    '(SELECT display_name FROM public_profiles WHERE user_id = ?1) AS curator_name, ' +
    '(SELECT COUNT(*) FROM list_follows WHERE list_id = ?2) AS follower_count').bind(row.user_id, row.id).first();
  return present({ ...row, ...meta });
}
function present(row) {
  // Explicit allowlist: never serialize SQL's user_id or raw profile joins.
  const name = row.curator_name ?? row.byline ?? '';
  const value = { id: row.id, title: row.title, description: row.description, byline: name,
    visibility: row.visibility, published: row.visibility !== 'private',
    curator: { name, id: row.visibility === 'public' ? row.curator_id || null : null },
    follower_count: row.follower_count || 0, version: row.version, created_at: row.created_at, updated_at: row.updated_at };
  if (row.keys_json !== undefined) value.keys = JSON.parse(row.keys_json);
  else value.count = row.count;
  return value;
}
function normalizeId(id) { const value = id.toUpperCase(); return ID_RE.test(value) ? value : ''; }
function newId() { return [...crypto.getRandomValues(new Uint8Array(12))].map(byte => ALPHABET[byte & 31]).join(''); }
function empty() { return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } }); }
function json(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: {
    'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
  } });
}
