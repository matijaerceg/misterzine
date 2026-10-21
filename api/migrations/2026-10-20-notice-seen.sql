-- Site notices (docs/theme.js NOTICE): remember per account which notice was closed.
-- Apply once to a database created before 2026-10-20:
--   npx wrangler d1 execute misterzine --remote --file=migrations/2026-10-20-notice-seen.sql
-- (--local for the wrangler dev database). Fresh databases get the column from schema.sql.
ALTER TABLE users ADD COLUMN notice_seen TEXT;
