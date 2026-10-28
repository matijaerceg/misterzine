CREATE TABLE IF NOT EXISTS list_moderation (
  list_id TEXT PRIMARY KEY REFERENCES curated_lists(id) ON DELETE CASCADE,
  hidden INTEGER NOT NULL CHECK (hidden IN (0,1)),
  reason TEXT NOT NULL DEFAULT '',
  moderated_by INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
