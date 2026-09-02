# misterzine account service

A single Cloudflare Worker (`src/index.js`) with a D1 database (`schema.sql`).
It signs visitors in with Google or GitHub and stores their release-tracker
favorites. Nothing else: no passwords, no names, no device addresses, no keys.
The site talks to it from the browser at `https://api.misterzine.fyi`.

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
