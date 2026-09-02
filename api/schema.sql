-- misterzine account service: D1 (SQLite) schema.
-- Apply with: npx wrangler d1 execute misterzine --remote --file=schema.sql
-- (add --local for the wrangler dev database). Idempotent.

CREATE TABLE IF NOT EXISTS users (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  provider         TEXT    NOT NULL,            -- 'google' | 'github'
  provider_user_id TEXT    NOT NULL,            -- the provider's stable user id (Google sub / GitHub id)
  email            TEXT,                        -- support lookups only; never displayed or mailed
  created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (provider, provider_user_id)
);

CREATE TABLE IF NOT EXISTS favorites (
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key      TEXT    NOT NULL,                    -- release tracker row key (data.json `k`)
  added_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash   TEXT    PRIMARY KEY,             -- sha256 hex of the bearer token
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  last_seen_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
