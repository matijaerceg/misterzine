-- Safe to re-run. The original custom_lists table must exist (apply schema.sql
-- or the first Custom Lists migration). No column-altering statements needed.
CREATE TABLE IF NOT EXISTS public_profiles (
  user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  id           TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS curated_lists (
  id          TEXT PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  byline      TEXT NOT NULL DEFAULT '',
  keys_json   TEXT NOT NULL DEFAULT '[]',
  visibility  TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'unlisted', 'public')),
  version     INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS curated_lists_user_updated ON curated_lists(user_id, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS curated_lists_directory ON curated_lists(visibility, updated_at DESC, id);
CREATE TABLE IF NOT EXISTS list_follows (
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  list_id    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (user_id, list_id)
);
-- list_id has no foreign key: followers retain an unavailable entry after
-- withdrawal or deletion, without retaining the title or other list content.
CREATE INDEX IF NOT EXISTS list_follows_target ON list_follows(list_id);

-- Existing shared links stay unlisted. Never opt old lists into discovery.
-- Keep a legacy byline only until its owner explicitly chooses an account name.
-- The original table is emptied after a successful copy, so repeated runs
-- cannot resurrect a deleted list or overwrite edits in the new table.
INSERT INTO curated_lists (id, user_id, title, description, byline, keys_json, visibility, version, created_at, updated_at)
  SELECT id, user_id, title, description, byline, keys_json,
    CASE WHEN published = 1 THEN 'unlisted' ELSE 'private' END, version, created_at, updated_at
  FROM custom_lists WHERE true ON CONFLICT(id) DO NOTHING;
DELETE FROM custom_lists;
