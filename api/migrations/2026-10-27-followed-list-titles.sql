-- Remember only a followed list's title, never its games or description.
CREATE TABLE IF NOT EXISTS list_follow_titles (
  user_id INTEGER NOT NULL,
  list_id TEXT NOT NULL,
  title TEXT NOT NULL,
  PRIMARY KEY (user_id, list_id),
  FOREIGN KEY (user_id, list_id) REFERENCES list_follows(user_id, list_id) ON DELETE CASCADE
);
INSERT OR IGNORE INTO list_follow_titles (user_id, list_id, title)
SELECT f.user_id, f.list_id, l.title FROM list_follows f JOIN curated_lists l ON l.id = f.list_id
WHERE l.visibility IN ('public', 'unlisted');
