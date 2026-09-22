# misterzine account service

A single Cloudflare Worker (`src/index.js`) with a D1 database (`schema.sql`).
It signs visitors in with Google or GitHub and stores their release-tracker
favorites: no passwords, no names, no device addresses, no keys.
The site talks to it from the browser at `https://api.misterzine.fyi`.

It also takes the diagnostic reports players send from the MisterZine
Frontend (Options -> Troubleshooting -> Send a report), in `src/reports.js`:
see [Device reports](#device-reports).

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
and shows them a four-character code such as `K7Q2`. The report holds no account and no
IP address; the rate limiter keys on the address in memory only. Only the
developer can read reports, with the `REPORTS_TOKEN` secret.

Reports live in the private R2 bucket `misterzine-reports`, never the public
image bucket. Its lifecycle rule deletes each one 30 days after upload, and the
read routes refuse anything older, since the rule runs about once a day.
Codes are four Crockford base32 characters, about a million of them. An
upload claims its code with a put that succeeds only while the key is free, so
two uploads never share one. A code can be drawn again once its report has
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
python api/get_report.py K7Q2             # print it; a copy lands in .secrets/reports/
python api/get_report.py --list           # the last 30 days
python api/get_report.py --delete K7Q2
```

The routes are tested with `npm test` (vitest with the Workers pool, local R2).
