# misterzine account service

A single Cloudflare Worker (`src/index.js`) with a D1 database (`schema.sql`).
It signs visitors in with Google or GitHub and stores their release-tracker
favorites and custom game lists: no passwords, no OAuth names, no device
addresses, no Zaparoo keys. Accounts can have a public curator name the owner chooses.
The site talks to it from the browser at `https://api.misterzine.fyi`.

It also takes the diagnostic reports players send from the MisterZine
Frontend (Options -> Troubleshooting -> Send a report), in `src/reports.js`:
see [Device reports](#device-reports). And it takes the site's feedback form,
in `src/feedback.js`: see [Site feedback](#site-feedback).

The full route list and the security model are at the top of `src/index.js`.
The user-facing description is the site's [privacy page](../docs/privacy/index.html).

## One-time setup

Prerequisites: the `misterzine.fyi` zone on Cloudflare DNS (registrar can stay
at Porkbun), a Google Cloud OAuth client, and a GitHub OAuth App.

Provider callback URLs (enter these when creating the OAuth apps):

- Google: `https://api.misterzine.fyi/auth/google/callback`
- GitHub: `https://api.misterzine.fyi/auth/github/callback`

Google's consent screen needs the privacy policy URL `https://misterzine.fyi/privacy/`
and only the `openid` and `email` scopes (no app verification needed for those).
The GitHub app needs no extra permissions.

Then, from this folder, once (`npx wrangler` downloads Wrangler on first use):

```bash
npx wrangler login
npx wrangler d1 create misterzine
```

Paste the printed `database_id` into `wrangler.toml`, then:

```bash
npx wrangler d1 execute misterzine --remote --file=schema.sql
npx wrangler secret put GOOGLE_CLIENT_ID
npx wrangler secret put GOOGLE_CLIENT_SECRET
npx wrangler secret put GITHUB_CLIENT_ID
npx wrangler secret put GITHUB_CLIENT_SECRET
npx wrangler secret put SESSION_SECRET
npx wrangler deploy
```

`SESSION_SECRET` is any long random string (it signs the short-lived sign-in
cookie). Each `secret put` prompts for the value; nothing is typed into a file.

`wrangler deploy` also attaches the custom domain from `wrangler.toml`
(`api.misterzine.fyi`); Cloudflare creates the DNS record and certificate itself.

Recommended, in the Cloudflare dashboard: a rate-limiting rule on
`api.misterzine.fyi` (for example 60 requests per minute per IP). The Worker
caps favorites at 5000 per account and validates every key, so abuse stays boring.

## Redeploying after a code change

```bash
npx wrangler deploy
```

## Local development

Create `api/.dev.vars` (gitignored) with the five secret names above (the OAuth
values can be a second pair of apps whose callbacks point at
`http://localhost:8787/auth/...`; for favorites-only testing they can be dummies).
Then:

```bash
npx wrangler d1 execute misterzine --local --file=schema.sql
npx wrangler dev
```

The API listens on `http://localhost:8787`. To let a locally served copy of the
site call it, add that site's origin to `DEV_ORIGINS` in `wrangler.toml` for the
session (do not commit it). A session for testing without OAuth: insert a row
into `sessions` with the sha256 of any token and use that token as the bearer.

## Custom lists, public names and following

An account can own any number of ordered lists of exact Tracker `k` values.
Lists start **private** (owner only). **Unlisted** lists can be read by anyone
with their ID; **public** lists also appear in the directory and curator page.
Changing visibility never changes a list's ID. The current Arcade app does
not subscribe to these lists yet.

A curator chooses one public display name for the account using
`PUT /me/profile {"display_name":"Matija"}`. It returns a top-level
`{"id":"3PK4H7X2RC9N","display_name":"Matija"}`; `GET /me` includes that object
as `profile`, or `null` until a name has been chosen. The name is trimmed,
1–80 UTF-16 units, need not be unique, and is never filled from OAuth name,
provider ID or email. The random public profile ID stays stable through renames.
Profile request bodies are capped at 4 KiB. Invalid names return
`400 {"error":"bad_display_name"}`.

Owners must choose a name before saving a list as unlisted or public;
otherwise that save returns `409 {"error":"profile_required"}`. The chosen
name appears on every list. It is public text even on unlisted links, but
only public lists reveal the profile ID and link to the curator page.
Changing the name does not change any list's version or content-update date.
Old per-list `byline` inputs are ignored. The response field remains for
compatibility and reflects the account name.

Full list responses (owner and anonymous read) use this shape:

```json
{
  "id": "4PY7H2M8VC3N",
  "title": "Favourite games",
  "description": "A few arcade favourites.",
  "byline": "Matija",
  "keys": ["galaga", "pacman"],
  "visibility": "public",
  "published": true,
  "curator": {"name": "Matija", "id": "3PK4H7X2RC9N"},
  "follower_count": 3,
  "version": 2,
  "created_at": "2026-10-22T15:00:00.000Z",
  "updated_at": "2026-10-22T15:10:00.000Z"
}
```

`published` is a transitional boolean: true for either unlisted or public.
`curator.id` is always `null` on private/unlisted lists. Neither list nor
profile responses contain account IDs, emails, OAuth identities or follower
identities. Summaries have the same fields except `keys`, replaced by `count`.
Follower counts include unique accounts following that list, including while
it is private. No follower identities are exposed.

List and profile IDs are twelve cryptographically random uppercase Crockford
base32 characters (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`); lookup accepts lowercase.
List keys are case-sensitive, kept in curator order, and deduplicated by first
occurrence. Up to 5000 submitted keys are allowed, each matching
`[A-Za-z0-9_-]{1,64}`. The Worker intentionally accepts keys absent from the
current catalogue, so clients can preserve and explain unavailable selections.
Title is 1–100 UTF-16 units after trimming; description at most 2000. Display
fields are stored trimmed and clients must render them as text. List request
bodies are capped at 384 KiB including streamed bodies.

All owner and following routes use `Authorization: Bearer <session>`:

| Route | Request | Result |
|---|---|---|
| `GET /lists` | — | `200 {"lists":[summaries]}`: own lists, latest content update first |
| `POST /lists` | `{title, description?, keys?}` | `201` full private list, version 1; optional values default to `""` and `[]` |
| `GET /lists/:id` | — | `200` full owned list; another owner's list returns `404`, including when public |
| `PUT /lists/:id` | `{title, description?, keys, visibility, version}` | `200` full updated list |
| `DELETE /lists/:id` | `{version}` | `204`; removes the list; followers retain an unavailable entry |
| `GET /collections` | — | `200 {"owned":[summaries],"following":[summaries or unavailable entries]}` |
| `PUT /following/:id` | no body needed | `204`, idempotent; follows an accessible public/unlisted list |
| `DELETE /following/:id` | no body needed | `204`, idempotent even when the target is unavailable |
| `GET /public/lists/:id` | anonymous | `200` full public/unlisted list; `404` if private, deleted or unknown |
| `GET /public/lists` | anonymous; query described below | `200 {"lists":[summaries],"total":42,"has_more":true}`; public only |
| `GET /public/curators/:id` | anonymous | `200 {"profile":{"id":"...","display_name":"..."},"lists":[public summaries]}`; `404` if no public lists |

Following one's own list returns `400 {"error":"own_list"}`. Following an
unknown/private/deleted list returns `404`. There is one follow per account
and list, enforced by the database even during simultaneous requests.
`GET /collections` never returns private content from followed lists: when
a target becomes private or is deleted, the entry is exactly
`{"id":"4PY7H2M8VC3N","unavailable":true}`. If the same list becomes accessible
again, its live summary returns automatically. Followed summaries are ordered
by follow time (newest first), with ID breaking ties.

The directory accepts `q` (trimmed, at most 200 units; literal substring of
title, description or curator name), `sort=updated|created|followers`
(default `updated`), `offset=0..10000` (default 0), and `limit=1..100` (default
24). Invalid values return `400 {"error":"bad_query"}`. Searches are
case-insensitive for ASCII. Every sort is descending and has deterministic
ID tie-breaking; follower sorting also uses update date before ID. Only
public lists participate in search, totals, pagination and curator pages.

`PUT` and `DELETE` require the last-read positive integer version. Comparison
and mutation happen in one database statement. A stale request, including a
stale no-op, returns `409 {"error":"conflict","current_version":2}` without
changing anything. Reload the complete list before deciding how to merge;
never retry blindly using `current_version`.

A save that changes neither title, description, key order nor visibility
preserves both version and `updated_at`. Visibility-only changes increment
version but preserve `updated_at`, so repeatedly sharing or withdrawing a list
does not move it up the recently updated directory. Content changes increment
version and set `updated_at`. For older clients, when `visibility` is absent,
`published:true` means **unlisted**, and false means private. Explicit visibility
wins when both fields are sent.

Other list errors are `400` with `bad_json`, `bad_title`, `bad_description`,
`bad_keys`, `bad_visibility` or `bad_version`; `401 unauthorized`; `404 not_found`;
and `413 too_large`. ID allocation can return `503 unavailable` after repeated
collisions. All routes use existing site/DEV_ORIGINS CORS and `Cache-Control:
no-store`, so withdrawal takes effect on the next request.

Deleting an account transactionally removes its owned lists, chosen profile,
its own follows, favorites and sessions. Other accounts' follows of its lists
remain only as unavailable IDs, without the deleted content.

### Database migration and local testing

The latest schema uses `curated_lists`, `public_profiles` and `list_follows`.
`list_follows.list_id` deliberately has no foreign key, preserving unavailable
entries without preserving list content. The original `custom_lists` table
is retained empty only as an upgrade source.

`migrations/2026-10-22-list-community.sql` creates the new tables, copies old
lists without overwriting any existing new row, then empties the old table.
It maps previously published lists to **unlisted**, never directory-public.
Their existing bylines remain fallback display text until the owner chooses
an account name; the migration never guesses an account profile from old
per-list names. Existing links keep working. Subsequent nonprivate saves
require the chosen account name.

The migration is idempotent: after the copy, the old table is empty, so a
later run cannot reintroduce a deleted list. `schema.sql` includes the same
upgrade and works for both fresh and existing local databases. Before any
production change, back up the database and apply schema/migrations before
deploying this Worker and then the site. From `api/`:

```bash
# Local-only database, safe for staging without touching live accounts:
npx wrangler d1 execute misterzine --local --file=schema.sql
npm test

# Only when deployment is approved; also handles a database predating lists:
npx wrangler d1 execute misterzine --remote --file=schema.sql
npx wrangler deploy
```

The new Worker needs all three tables even when the Lists UI is not visible,
because `/me` and account deletion use them. An old Worker reads the now-empty
legacy table: rolling its code back is not a data migration rollback. Preserve
the new tables and restore a compatible Worker instead. A locally served page
using the production API still writes production data; use the preview helper
or Wrangler local D1 and disposable sessions for staging.

## Device reports

When a player chooses Options -> Troubleshooting -> Send a report, the Frontend
uploads a plain-text description of their card (`POST /reports`: app version,
settings, filters, which game files are not listed and why, recent log lines)
and shows them a four-character code such as `K7M4`. The report holds no account and no
IP address; the rate limiter keys on the address in memory only. Only the
developer can read reports, with the `REPORTS_TOKEN` secret.

Reports live in the private R2 bucket `misterzine-reports`, never the public
image bucket. Its lifecycle rule deletes each one 30 days after upload, and the
read routes refuse anything older, since the rule runs about once a day.
Codes are four characters from `34679ACEFHJKMNPRTWXY`, which leaves out every
character something else could be mistaken for (0/O/Q/D, 1/I/L, 2/Z, 5/S, 8/B,
6/G, U/V): 160,000 codes. Reading still accepts the Crockford base32 codes
issued before the alphabet narrowed. An upload claims its code with a put that
succeeds only while the key is free, so two uploads never share one. A code can be drawn again once its report has
expired, which is why `get_report.py` prints each report's upload date.
`REPORTS_ENABLED = "0"` in `wrangler.toml` switches uploads off (503) without
an app release; `REPORT_MAX_BYTES` caps their size.

One-time setup, from this folder:

```bash
npx wrangler r2 bucket create misterzine-reports
npx wrangler r2 bucket lifecycle add misterzine-reports expire-30d --expire-days 30 -y
npx wrangler secret put REPORTS_TOKEN
npx wrangler deploy
```

Keep the same token in `.secrets/reports.json` as `{"token": "..."}` in the main
checkout (gitignored). Then:

```bash
python api/get_report.py K7M4             # print it; a copy lands in .secrets/reports/
python api/get_report.py --list           # the last 30 days
python api/get_report.py --delete K7M4
```

## Site feedback

The feedback form on the site posts to `POST /feedback`. Each message is
stored in the D1 table `feedback` and then forwarded to a private Discord
channel through a webhook. If Discord is down or the webhook is missing, the
message is still stored, the visitor still sees success, and the row keeps
`discord_ok = 0`. Anonymous messages work; when the request carries a valid
session (`Authorization: Bearer <mz-token>`) the account id is recorded too.

What a row holds: the text, the optional contact box (email or Discord
handle, as typed), the page, the tracker row key, the theme, the account id if
signed in, the first 256 characters of the User-Agent, and `ip_hash`, an HMAC
of the sender's address keyed with `SESSION_SECRET` (IPv6 cut to its /64).
Never the address itself. Rotating `SESSION_SECRET` only resets the rate-limit
history, since old hashes stop matching.

The request, JSON:

| field | | |
|---|---|---|
| `text` | required | 1 to 4000 characters after trimming; at most 5 links (`http://`, `https://`, `www.`) across text and contact |
| `contact` | optional | at most 200 characters |
| `page` | optional | the page URL; kept only when it is on the site's own origin (or a `DEV_ORIGINS` one), cut to 500 characters |
| `key` | optional | the tracker row key (data.json `k`), dropped if it is not one |
| `theme` | optional | the theme slug, dropped if it is not `[A-Za-z0-9_-]{1,32}` |
| `website` | honeypot | hide it from people; anything in it answers success and stores nothing |

The answers: `201 {"ok":true}`; `400 {"error": "no_text" | "text_too_long" |
"too_many_links" | "contact_too_long" | "bad_contact" | "bad_json"}`;
`403 {"error":"origin"}` for a browser on another site; `413 {"error":"too_large"}`
over 32 KB; `429 {"error":"rate_limited","retry_after":<seconds>}` (also a
`Retry-After` header); `503 {"error":"disabled"}` when `FEEDBACK_ENABLED` is
not `"1"` in `wrangler.toml`.

Limits, per address: 5 messages in any 10 minutes and 30 in any 24 hours,
counted from the stored rows (refused and honeypot requests do not count).
The count and the insert are one SQL statement, so a burst cannot slip past.

One-time setup, from this `api/` folder (never the repo root). The table must
exist before the new code is deployed, or the form answers 500:

```bash
npx wrangler d1 execute misterzine --remote --file=schema.sql   # adds the feedback table; safe to re-run
npx wrangler secret put DISCORD_FEEDBACK_WEBHOOK                # prompts; paste the webhook URL yourself
npx wrangler deploy
```

## Site notices

The site shows a dated notice card (`docs/theme.js`, the `NOTICE` block at the
top: id, first and last day, text). Closing it is remembered in the browser,
and for a signed-in visitor on the account too (`PUT /me/notice {id}`, read
back as `notice` in `GET /me`), so a new notice shows once per person, not once
per browser. A database created before 2026-10-20 needs the column once, before
the code is deployed:

```bash
npx wrangler d1 execute misterzine --remote --file=migrations/2026-10-20-notice-seen.sql
npx wrangler deploy
```

The webhook URL comes from Discord: the channel's Edit Channel ->
Integrations -> Webhooks -> New Webhook -> Copy Webhook URL. Treat it as a
password (anyone holding it can post to the channel); it lives only in the
Worker secret, never in a file.

Test after deploying (it counts toward your own address's limit):

```bash
curl -i https://api.misterzine.fyi/feedback -H 'Content-Type: application/json' -d '{"text":"Test from curl, please ignore","contact":"me"}'
```

That answers `201 {"ok":true}` and the message appears in the Discord channel.

Reading every message (the `REPORTS_TOKEN` is the same developer key as for
device reports; `?since=<id>` returns only newer ones):

```bash
curl -s https://api.misterzine.fyi/feedback/export -H "Authorization: Bearer $REPORTS_TOKEN"
```

Or without the token, straight from D1:

```bash
npx wrangler d1 execute misterzine --remote --json --command "SELECT * FROM feedback ORDER BY id"
npx wrangler d1 execute misterzine --remote --command "DELETE FROM feedback WHERE id = 1"   # drop a test message
```

To switch the form off without a code change, set `FEEDBACK_ENABLED = "0"` in
`wrangler.toml` and deploy. For `wrangler dev`, `.dev.vars` needs
`SESSION_SECRET`; `DISCORD_FEEDBACK_WEBHOOK` is optional, and the locally
served site's origin must be in `DEV_ORIGINS`.

## Tests

The report, feedback, notice and custom-list routes are tested with `npm test`
(Vitest with the Workers pool, local R2 and D1; database tests apply `schema.sql`
themselves). List coverage includes account isolation, explicit public fields,
publication and withdrawal, simultaneous saves, stale-delete protection,
validation/body limits, profile names, visibility, public directory pagination, following races and withdrawal, no-op saves, migration reruns, account deletion and existing CORS behavior.


## List moderation

Apply `migrations/2026-10-28-list-moderation.sql` before deploying this Worker.
It is idempotent; `schema.sql` includes it for new databases. No production
migration or deployment is performed by the local preview tooling.

`GET /me` returns `list_admin`. Every `/admin/lists` request checks the Google
OAuth account with verified email `matija.erceg@gmail.com`. GitHub emails and
client-supplied fields never grant access. Login refreshes or clears the stored email.

- `GET /admin/lists?q=...&offset=0&hidden=1`: 24 summaries plus `has_more`;
  includes private/unlisted lists; optional hidden-only filter and literal search.
- `GET /admin/lists/:id`: inspect a list regardless of visibility.
- `PUT /admin/lists/:id`: `{hidden, reason, version}`. Hiding requires a reason
  (up to 500 characters). A stale content version returns 409.

The override is independent of author visibility: editing or republishing cannot
remove it. Public reads, discovery, curator pages, follows and pins exclude hidden
content. Owners can edit/delete their hidden lists and see the reason. Restore
honors current visibility; it does not automatically publish. The latest action
records moderator ID, reason and time; deletion cascades this record. This is
reversible moderation, not an immutable audit log or account ban.

The preview has a separate `/__preview__/admin` fixture login, seeded only in
local D1. Production has no preview bypass.

Moderation UI lives in Browse and the full list view, enabled by the admin-only
Menu toggle. Its local preference synchronizes between tabs; it never grants
server permission. Browse's hidden-only mode requests `hidden=1&shared=1` to omit
private drafts, with normal search/pagination/sort. There is no separate admin page.


## List abuse limits

Apply `migrations/2026-10-28-list-write-limits.sql` before deploying this version
(or apply the complete idempotent schema for a database without lists yet).
Accounts can own up to 200 lists (atomic quota, 409 `list_limit`). Creating,
copying, editing, deleting, following, pinning, profile edits and moderation share
120 writes/minute/account. New-list attempts also have a 20/hour/account limit.
Durable D1 fixed-window counters return 429 `rate_limited` with Retry-After.
Reads and favorites are unaffected. Counters contain no IP addresses and cascade
on account deletion. These are initial per-account safeguards, not protection
against coordinated multi-account abuse.
