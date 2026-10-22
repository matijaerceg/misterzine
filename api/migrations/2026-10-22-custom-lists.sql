-- Safe to re-run. Apply before deploying the Custom Lists Worker.
CREATE TABLE IF NOT EXISTS custom_lists (
  id          TEXT PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  byline      TEXT NOT NULL DEFAULT '',
  keys_json   TEXT NOT NULL DEFAULT '[]',
  published   INTEGER NOT NULL DEFAULT 0 CHECK (published IN (0, 1)),
  version     INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS custom_lists_user_updated ON custom_lists(user_id, updated_at DESC, id);
