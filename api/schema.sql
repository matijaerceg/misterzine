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

-- Site feedback form (src/feedback.js). Added 2026-10-07: re-running this
-- whole file on the live database only creates what is missing.
CREATE TABLE IF NOT EXISTS feedback (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT    NOT NULL,                  -- ISO 8601 UTC, whole seconds
  text       TEXT    NOT NULL,                  -- the message, 1 to 4000 characters
  contact    TEXT,                              -- optional email or Discord handle, as typed
  page       TEXT,                              -- the site page it was sent from
  row_key    TEXT,                              -- release tracker row open at the time (data.json `k`)
  theme      TEXT,                              -- the site theme in use
  account_id INTEGER,                           -- users.id when signed in (kept if the account is deleted)
  ip_hash    TEXT    NOT NULL,                  -- HMAC of the address (IPv6 cut to its /64), never the address
  user_agent TEXT,                              -- first 256 characters
  discord_ok INTEGER NOT NULL DEFAULT 0         -- 1 once the Discord webhook accepted it
);

CREATE INDEX IF NOT EXISTS feedback_ip_time ON feedback(ip_hash, created_at);
