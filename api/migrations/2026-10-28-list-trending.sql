-- Retain the first follow time to prevent unfollow/refollow ranking boosts.
-- No titles or list contents are retained. Account/list deletion removes history.
CREATE TABLE IF NOT EXISTS list_follow_history (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  list_id TEXT NOT NULL REFERENCES curated_lists(id) ON DELETE CASCADE,
  first_followed_at TEXT NOT NULL,
  PRIMARY KEY (user_id, list_id)
);
INSERT OR IGNORE INTO list_follow_history (user_id, list_id, first_followed_at)
SELECT f.user_id, f.list_id, f.created_at FROM list_follows f
JOIN curated_lists l ON l.id = f.list_id;
