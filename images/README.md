# misterzine image service

A Cloudflare Worker (`src/index.js`) in front of an R2 bucket. It serves arcade
screenshots by MAME setname to the [MisterZine Frontend](https://github.com/matijaerceg/misterzine-on-device)
for games it finds on a card that the catalogue does not list:

    GET https://images.misterzine.fyi/snap/<setname>.png    in-game shot
    GET https://images.misterzine.fyi/title/<setname>.png   title screen
    GET https://images.misterzine.fyi/healthz

The bucket is seeded once from the full [progettoSNAPS](https://www.progettosnaps.net/)
snap and title packs (`tools/seed_r2.py`), so a request is normally a plain read
served from Cloudflare's edge cache. A clone whose own set has no picture gets
its parent's (from MAME's clone table) and keeps a copy. With `UPSTREAM_ENABLED`
set to `"1"`, a miss may fetch the picture once from Arcade Database, then
libretro-thumbnails, and store it; misses are remembered for `NEG_TTL_DAYS`, so
no upstream ever sees the same setname twice, and `UPSTREAM_HOURLY_CAP` bounds
the total. Responses carry `X-Image-Width` and `X-Image-Height` so a client can
size a box before decoding.

Nothing about the requester is stored or logged; only upstream outcomes are.
The images remain the property of their owners and are hosted for
informational purposes, as on the site.

## One-time setup

Prerequisites: the `misterzine.fyi` zone on Cloudflare DNS, Node, and locally
7-Zip plus `pip install boto3` for the seeder.

```bash
cd images
npm install
npx wrangler login
npx wrangler r2 bucket create misterzine-images
npx wrangler deploy          # attaches images.misterzine.fyi from wrangler.toml
```

To try it on the `workers.dev` URL first, comment out the `routes` block.

Create an R2 API token (Object Read & Write, scoped to the bucket) and export
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (or put them in
`.secrets/r2.json`). Then, from the repo root:

```bash
python tools/seed_r2.py --meta                      # clone -> parent and description maps
python tools/seed_r2.py --pack snap --pack titles   # ~1.2 GB, 80k+ objects each; resumable
python tools/seed_r2.py --also-site                 # the site's own PNGs R2 lacks
```

Check `https://images.misterzine.fyi/healthz` for the seed summary, a parent
(`/snap/dkong.png`), a clone (`/snap/dkongj.png`) and a bad name (404, cacheable).

## Refreshing after a pack version bump

Bump the pack file names in `tools/fetch_images.py`, then:

```bash
python tools/seed_r2.py --pack snap --pack titles --force   # sends only changed bytes
python tools/seed_r2.py --purge-negatives                   # forget remembered misses
```

Newly added images may stay cached as 404 at an edge location for up to a day.

## Turning the miss path on

After a week of watching 404 counts in the Cloudflare analytics, set
`UPSTREAM_ENABLED = "1"` in `wrangler.toml` and `npx wrangler deploy`. Add a
rate-limiting rule for `images.misterzine.fyi` in the dashboard (for example
300 requests per minute per IP).

## Tests and local development

```bash
npm test          # vitest with a local R2 simulation and mocked upstreams
npx wrangler dev  # local server; seed one object with
npx wrangler r2 object put misterzine-images/snap/dkong.png --file ../docs/images/snap/dkong.png --local
```

The tests run as two projects, one per `UPSTREAM_ENABLED` value, with the
edge cache bypassed (`EDGE_CACHE=0`; the Cache API write does not settle in
the test runtime). In a synced folder, Vite's dependency cache can hit a file
lock; set `VITEST_CACHE_DIR` to a local path when that happens.
