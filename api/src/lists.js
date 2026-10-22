// Account-owned, ordered selections of Tracker row keys. Publication exposes
// only the list's explicit display fields, never any OAuth account identity.
// One row holds the complete selection so version-checked changes are atomic.
import { readCapped } from './reports.js';

const KEY_RE = /^[A-Za-z0-9_-]{1,64}$/;
const ID_RE = /^[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{12}$/;
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const BODY_MAX = 384 * 1024; // 5000 maximum-length row keys plus display fields
const FIELDS = 'id, title, description, byline, keys_json, published, version, created_at, updated_at';

export async function publicList(env, path, method) {
  const match = path.match(/^\/public\/lists\/([^/]+)$/);
  const id = match && normalizeId(match[1]);
  if (method !== 'GET' || !id) return json({ error: 'not_found' }, 404);
  const row = await env.DB.prepare('SELECT ' + FIELDS + ' FROM custom_lists WHERE id = ? AND published = 1').bind(id).first();
  return row ? json(full(row)) : json({ error: 'not_found' }, 404);
}

export async function lists(request, env, method, path, user) {
  if (path === '/lists' && method === 'GET') {
    // Summaries do not load every list's selection into Worker memory.
    const { results } = await env.DB.prepare(
      'SELECT id, title, description, byline, published, version, created_at, updated_at, ' +
      'json_array_length(keys_json) AS count FROM custom_lists WHERE user_id = ? ORDER BY updated_at DESC, id'
    ).bind(user.id).all();
    return json({ lists: results.map(row => ({ ...row, published: !!row.published })) });
  }
  if (path === '/lists' && method === 'POST') {
    const parsed = await body(request);
    if (parsed.error) return json({ error: parsed.error }, parsed.status);
    const value = validate(parsed.value, false);
    if (value.error) return json({ error: value.error }, 400);
    // A collision retries without overwriting another curator's list. Other
    // database failures still propagate, rather than being mistaken for one.
    for (let attempt = 0; attempt < 5; attempt++) {
      const row = await env.DB.prepare(
        'INSERT INTO custom_lists (id, user_id, title, description, byline, keys_json) VALUES (?, ?, ?, ?, ?, ?) ' +
        'ON CONFLICT(id) DO NOTHING RETURNING ' + FIELDS
      ).bind(newId(), user.id, value.title, value.description, value.byline, JSON.stringify(value.keys)).first();
      if (row) return json(full(row), 201);
    }
    return json({ error: 'unavailable' }, 503);
  }

  const match = path.match(/^\/lists\/([^/]+)$/);
  const id = match && normalizeId(match[1]);
  if (!id || !['GET', 'PUT', 'DELETE'].includes(method)) return json({ error: 'not_found' }, 404);
  if (method === 'GET') {
    const row = await env.DB.prepare('SELECT ' + FIELDS + ' FROM custom_lists WHERE id = ? AND user_id = ?').bind(id, user.id).first();
    return row ? json(full(row)) : json({ error: 'not_found' }, 404);
  }

  const parsed = await body(request);
  if (parsed.error) return json({ error: parsed.error }, parsed.status);
  if (!validVersion(parsed.value.version)) return json({ error: 'bad_version' }, 400);
  if (method === 'DELETE') {
    const row = await env.DB.prepare('DELETE FROM custom_lists WHERE id = ? AND user_id = ? AND version = ? RETURNING id')
      .bind(id, user.id, parsed.value.version).first();
    if (row) return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
  } else {
    const value = validate(parsed.value, true);
    if (value.error) return json({ error: value.error }, 400);
    const row = await env.DB.prepare(
      'UPDATE custom_lists SET title = ?, description = ?, byline = ?, keys_json = ?, published = ?, ' +
      "version = version + 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') " +
      'WHERE id = ? AND user_id = ? AND version = ? RETURNING ' + FIELDS
    ).bind(value.title, value.description, value.byline, JSON.stringify(value.keys), value.published ? 1 : 0,
      id, user.id, value.version).first();
    if (row) return json(full(row));
  }
  // Only the owner can learn that a conflict exists; another account sees the
  // same 404 as an unknown id, even when the list is published.
  const current = await env.DB.prepare('SELECT version FROM custom_lists WHERE id = ? AND user_id = ?').bind(id, user.id).first();
  return current ? json({ error: 'conflict', current_version: current.version }, 409) : json({ error: 'not_found' }, 404);
}

function validate(input, updating) {
  if (typeof input.title !== 'string' || !input.title.trim() || input.title.trim().length > 100)
    return { error: 'bad_title' };
  const description = input.description === undefined ? '' : input.description;
  const byline = input.byline === undefined ? '' : input.byline;
  if (typeof description !== 'string' || description.length > 2000) return { error: 'bad_description' };
  if (typeof byline !== 'string' || byline.length > 80) return { error: 'bad_byline' };
  const keys = !updating && input.keys === undefined ? [] : input.keys;
  if (!Array.isArray(keys) || keys.length > 5000 || !keys.every(key => typeof key === 'string' && KEY_RE.test(key)))
    return { error: 'bad_keys' };
  if (updating && typeof input.published !== 'boolean') return { error: 'bad_published' };
  return { title: input.title.trim(), description: description.trim(), byline: byline.trim(), keys: [...new Set(keys)],
    published: input.published, version: input.version };
}

async function body(request) {
  if (Number(request.headers.get('Content-Length')) > BODY_MAX) return { error: 'too_large', status: 413 };
  const bytes = await readCapped(request, BODY_MAX);
  if (!bytes) return { error: 'too_large', status: 413 };
  let value;
  try { value = JSON.parse(new TextDecoder().decode(bytes)); } catch (e) {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { error: 'bad_json', status: 400 };
  return { value };
}

function full(row) {
  const { keys_json, ...value } = row;
  return { ...value, keys: JSON.parse(keys_json), published: !!row.published };
}
function normalizeId(id) {
  const value = id.toUpperCase();
  return ID_RE.test(value) ? value : '';
}
function newId() {
  return [...crypto.getRandomValues(new Uint8Array(12))].map(byte => ALPHABET[byte & 31]).join('');
}
const validVersion = value => Number.isSafeInteger(value) && value > 0;
function json(value, status = 200) {
  // No public cache: unpublishing/removing a list takes effect on the next
  // request, and authenticated responses can never leak through shared caches.
  return new Response(JSON.stringify(value), { status, headers: {
    'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
  } });
}
