# 10k plan: accounts, Zaparoo launching, update_all

Written 2026-09-01. Discussion-only so far; nothing here is built.
Decisions below were approved in chat on 2026-09-01. Anything marked OPEN
still needs a call. Sessions implementing a piece: read this file first,
then the memory files it names, then work in a worktree (one session per
workstream, never two editing sessions in the main checkout).

## Approved decisions (do not re-litigate)

- Accounts: sign in with Google or GitHub only. No passwords, no email
  sending, no email/password accounts.
- Backend: one Cloudflare Worker at https://api.misterzine.fyi with a D1
  (SQLite) database. DNS for misterzine.fyi moves from Porkbun to
  Cloudflare (free; Porkbun stays registrar). The GitHub Pages records are
  recreated 1:1 on Cloudflare (4 A + 4 AAAA at apex, www CNAME), DNS-only
  (grey cloud) so Pages keeps serving and issuing its own certificate.
- Accounts store FAVORITES ONLY for now. No lists, no prefs, no devices.
- First login auto-imports the browser's local favorites into the account.
  No prompt.
- Server is the source of truth for signed-in users. Local storage is a
  paint cache. Writes are per item (add key / remove key), never the whole
  set. A failed write shows and reverts the star. No queue, no merge logic.
- Dedicated account page at /account/. Static privacy page at /privacy/.
  Delete-account lives on the account page.
- Saved MiSTers (LAN devices) and Zaparoo keys live ONLY in the visitor's
  browser storage. They are never sent to api.misterzine.fyi, in any form.
- Zaparoo launching is ADDED next to the existing LAN Remote path, not a
  replacement. A saved device is either kind; the launch row does not
  change shape.
- "My MiSTers" control always visible in the releases header. It opens the
  same device popover the launch row's manager button opens.
- update_all trigger ships for Zaparoo devices only (mister.script).
- Out of scope this round: named lists, per-core RSS feeds / OPML export,
  a 10k announcement banner, per-game search-to-launch, any change to the
  LAN Remote transport, any sync of device settings.

## Workstream 0: your tasks (credentials I must not create)

Do these early; several workstreams block on them.

1. Cloudflare: create a free account, add misterzine.fyi as a zone,
   recreate the current DNS records, switch nameservers at Porkbun.
   Verify https://misterzine.fyi still serves from GitHub Pages before
   anything else. (I can list the exact records to enter and verify after.)
2. Google Cloud: a project with an OAuth client (Web application).
   Authorized redirect URI: https://api.misterzine.fyi/auth/google/callback.
   The consent screen requires the privacy policy URL
   (https://misterzine.fyi/privacy/), so the privacy page must be LIVE
   before this step completes. Scopes: openid, email only. No app
   verification is needed for those.
3. GitHub: an OAuth App under your account. Callback:
   https://api.misterzine.fyi/auth/github/callback. Scope: none beyond
   the default (we read the public profile id and the primary email).
4. Hand me the four values (Google client id + secret, GitHub client id +
   secret) through the Cloudflare secrets UI or a wrangler secret command
   you run; I never need to see them in chat or in the repo.
5. Zaparoo test rig: the MisterPi ONLY (the DE10 is in use for other work).
   Core v2.17.0 is installed on the Pi (done 2026-09-01). Still yours: link
   it to your Zaparoo Online account (approve the code the Pi shows), then
   create a User API key with scopes devices:launch, read:devices,
   devices:scripts. Free tier allows one remote device; pick the Pi. The
   Pi is tate, so test launches are vertical games only.
6. Tell wizzo developers.zaparoo.com is still missing standalone.js (the
   spec loads, the page renders blank).

## Workstream A: backend (Cloudflare Worker + D1)

Memory to read: none yet (new territory). Write a memory file when done.

Shape: one Worker, one D1 database, wrangler config committed to the repo
under `api/` (secrets are NOT in the repo).

Routes:
- GET  /auth/google, /auth/github: start OAuth (state cookie, PKCE where
  the provider supports it), redirect to provider.
- GET  /auth/{provider}/callback: exchange code, find-or-create user keyed
  on (provider, provider_user_id), issue a session token, redirect to
  https://misterzine.fyi/auth/#t=<token>&new=1|0 (fragment, so the token
  never appears in a server log or GoatCounter).
- GET  /me: provider, created_at, favorites count. Requires token.
- GET  /favorites: array of row keys. Requires token.
- PUT  /favorites/{key}, DELETE /favorites/{key}: per-item writes.
  Idempotent. Requires token.
- POST /favorites/import: array of keys, union into the account. Called by
  the site exactly once, on first login (new=1). Requires token.
- POST /logout: revokes the token.
- DELETE /me: deletes favorites + user + sessions. Requires token and a
  confirm header set by the account page.

Data (D1):
- users(id, provider, provider_user_id, email, created_at) with a unique
  index on (provider, provider_user_id). Email is stored only so you can
  answer a support request; never displayed, never used to link accounts.
- favorites(user_id, key, added_at) primary key (user_id, key). `key` is
  the stable row key from _assign_row_keys (see memory deep-links).
- sessions(token_hash, user_id, created_at, last_seen_at). Long-lived
  (90 days), rotated on use, revocable.

Rules:
- CORS: allow origin https://misterzine.fyi only (plus http://localhost:*
  during local testing behind an env flag). Token goes in the
  Authorization header; no cookies on API calls, so no CSRF surface.
- Rate limit per token and per IP with Cloudflare's free rate-limiting
  rules. Favorites are cheap; 60 writes/min per user is generous.
- Validate keys against a pattern; reject unknown-shaped keys. Cap
  favorites per account (say 5000) to keep abuse boring.
- No analytics, no logging of tokens or emails.
- Free tier is ample: Workers 100k requests/day, D1 5M reads/day.

OPEN: none. Provider-linking (one account, two providers) is explicitly
NOT built; a person who signs in with the other provider gets a second,
empty account. The account page says which provider you are signed in
with, which makes this self-explanatory.

## Workstream B: accounts on the site

Memory to read: favorites-feature, favorites-updateall-export, deep-links,
theme-switcher-behavior, shared-nav-css, releases-layout-gotchas, pwa-install.

- Favorites store gets one seam: today `FAVS` is a Set persisted to
  localStorage `mz-favs` (docs/releases/index.html ~1057). Wrap add/remove
  behind functions that, when signed in, also PUT/DELETE to the API and
  revert the star on failure. Signed out: unchanged behavior. Everything
  downstream (favOnly, favView, ?fav= links, the favexp export dialog,
  Title-column padding) keeps reading `FAVS` and is untouched.
- Boot: if a token exists, paint from the local cache immediately, fetch
  /favorites, replace `FAVS` and the cache with the server set.
- First login (new=1): POST /favorites/import with the local set, then
  fetch. After that local is a cache. Sign out keeps the local copy as a
  plain local favorites set (the device keeps working); signing back in
  replaces it with the server set.
- /auth/ landing page (docs/auth/index.html): reads the fragment, stores
  the token, triggers the import if new, returns to the tracker (the
  referrer path is stored before starting sign-in). Tiny page, no styling
  beyond theme.css.
- Header: a "Sign in" control in the releases topbar next to Theme. Signed
  in it reads "Account" and links to /account/. This is the only place the
  release tracker mentions accounts; the landing and hardware pages get
  nothing (no favorites there).
- /account/ page (docs/account/index.html): signed-in provider, favorites
  count, a "backup / share link" (the existing favURL, so people have an
  export before deleting), Sign out, Delete account (two-step confirm,
  then DELETE /me, clears the token and the local cache), link to privacy.
  Signed out it shows the two sign-in buttons. Uses the shared nav.css and
  theme.css, no new visual language.
- /privacy/ page (docs/privacy/index.html): plain language. What is stored
  (provider id, email, favorites), why, that devices and Zaparoo keys stay
  in the browser, that deletion is immediate, no analytics beyond
  GoatCounter (which already exists), contact. Must be live before Google
  OAuth setup can complete.
- The ?fav= arrival banner: when signed in, "import these" adds to the
  account (per-item PUTs or one import call).
- PWA: test sign-in from the installed app on Android and iOS. iOS
  standalone apps have separate storage from Safari; a redirect that
  finishes in Safari would leave the app signed out. Test before ship; if
  it fails, the account page tells iOS app users to sign in inside the app.

## Workstream C: Zaparoo launching

Memory to read: launch-on-mister, zaparoo-online-user-api (the cloud
contract is fully verified there), update-all-trigger-idea, panel-drag-scroll,
motion-implementation-traps, verify-motion-not-endstates.

- Device model: `mz-misters` entries gain a kind. LAN: {n, h} as today.
  Zaparoo: {n, z: {key, dev}} where dev is the Zaparoo device short id.
  Existing entries without a kind are LAN. Nothing about devices ever
  leaves the browser.
- Add-device flow (the popover): two choices. "It's on this network"
  (current IP flow) and "Connect through Zaparoo". Order by browser:
  Chromium shows LAN first; Firefox, Safari and any Android browser show
  Zaparoo first with a "recommended for your browser" note. Zaparoo path:
  paste key, we call GET /v1/devices, list linked devices by name, pick
  one. That validates the key on the spot. The screen states the scopes to
  tick (devices:launch, read:devices; devices:scripts for update_all) and
  links to the Zaparoo Online User API page.
- "My MiSTers" header control on the releases page, always visible, opens
  the same popover (second anchor; the launch row's manager button keeps
  working). Reuse the metapop/closePop machinery and respect its traps
  (z-index 102, stopPropagation on re-render, launchrow exclusion).
- Launch through Zaparoo: POST /v1/devices/{dev}/operations then long-poll
  GET /v1/operations/{id}/wait?cursor=<revision>&timeout=25 until the
  target is terminal. Arcade rows: operation `launch`, value = the row's
  `mra` path. Non-arcade rows: `launch.system`, value = system id from a
  NEW map ZAP_SYS (Zaparoo systemdefs ids, wider than MISTER_SYS; rows
  that only Zaparoo can launch get a button only on Zaparoo devices).
  Deadline 60s default.
- Button states for Zaparoo devices: sending, launched, offline
  (unreachable), not found (media_not_found), busy, failed. LAN buttons
  keep the current fire-and-forget behavior; do not fake feedback there.
- Capability is per device: a row shows a device's button only if that
  device can launch that row.
- Same physical MiSTer may be saved twice (LAN and Zaparoo). No dedupe.
- Free-tier gate: a 403 on create means "this device is not your selected
  remote device"; say that in plain words on the button, once.
- Rate limits are not a concern at human pace (30 ops/min per key).
- DB9 users: `launch.system` honors `?launcher=`. Not exposed in UI this
  round; leave a hook (advanced arg on the device entry) and note it in
  the README.

## Workstream D: update_all trigger (Zaparoo devices only)

Depends on the on-device safety test in Workstream 0 step 5.

- Test first: run `mister.script` with value `update_all.sh` while a game
  is running and confirm whether Zaparoo refuses. If it does not, the
  site guards it: before firing, check GET /v1/play-sessions/active for
  that device (needs read:play_history; add to the scope list) and refuse
  with "finish your game first".
- UI: "Update cores" next to each Zaparoo device in the popover, plus a
  one-line shortcut on the new-since-last-visit notice ("run update_all on
  <device>") that opens the popover with that device highlighted.
- One confirm tap ("Run update_all on Living Room? Takes 5 to 20 minutes
  and uses the MiSTer's screen"). Button locks after firing and shows
  "started"; the operation result only confirms the script launched, not
  that it finished. Never offer cancel (the Remote kill endpoint orphaned
  scripts; Zaparoo has no cancel either).
- Nothing for LAN devices.

## Workstream E: words

- README: launch section rewritten around two ways to connect, Zaparoo
  setup steps a non-technical owner can follow (install Core, link,
  toggle, key with exact scopes, paste), the free-tier one-device note,
  update_all notes, DB9 launcher hook. Accounts section: what is stored,
  link to /privacy/.
- CHANGELOG.md: one entry per shipped piece, same push, plain ASCII, the
  page is a "release tracker".
- Memory files: new ones for the backend and the account model; update
  launch-on-mister, favorites-feature, update-all-trigger-idea, and
  MEMORY.md as each piece ships.
- Ask wizzo (after ship): a note that misterzine now launches through
  Zaparoo Online, and that the installed-cores read is the one wishlist
  item still open.

## Order and shippability

Each phase is independently shippable and testable locally first
(memory: always-push-live, local-test-server-launch-and-verify).

1. Zaparoo launching (Workstream C). Pure client side, no external setup
   beyond your DE10 test rig. Ship it alone.
2. Privacy page, then your OAuth/Cloudflare tasks, then the backend
   (Workstream A), then accounts on the site (Workstream B). Ship together.
3. update_all trigger (Workstream D), after the safety test.
4. Words land with each phase, not at the end.

Parallel sessions: A and C do not touch the same files (api/ vs
docs/releases/index.html) and can run concurrently in separate worktrees.
B and C both edit docs/releases/index.html; run them sequentially, C first.

## Test checklist (before any push)

- Zaparoo: launch an arcade MRA and a console system on the DE10 from
  Chrome, Firefox, and the Android PWA; unplug the DE10 and confirm the
  button says offline; wrong key shows a clear error; free-tier 403 shows
  a clear message.
- Accounts: sign in with both providers on desktop and the Android PWA and
  iOS (Safari and installed app); first login imports local favorites;
  star, refresh, star persists; second device shows the same set; failed
  write reverts the star; sign out keeps local copy; delete account wipes
  server and local, /me returns 401 afterwards.
- update_all: fires only from menu; refuses mid-game (device- or
  site-side); button locks; TV shows the script running.
- Existing behavior unchanged: ?fav= links, favexp export dialog, LAN
  launches on both transports, filters, deep links, feeds byte-identical.
