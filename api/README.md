# misterzine account service

A single Cloudflare Worker (`src/index.js`) with a D1 database (`schema.sql`).
It signs visitors in with Google or GitHub and stores their release-tracker
favorites: no passwords, no names, no device addresses, no keys.
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

The report and feedback routes are tested with `npm test` (vitest with the
Workers pool, local R2 and D1; the feedback tests apply `schema.sql` themselves).
