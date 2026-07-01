# misterzine

A local release database for **MiSTer FPGA** cores — arcade-focused — built to feed an
automated zine. It answers two questions:

- **Retrospective:** which titles exist, when did each core *debut* on MiSTer, and when
  was it last updated? (Real dates going back to **2017**.)
- **Going forward:** what's *new or updated* since the last check, with a date stamp?

## TL;DR — what you get right now

After the initial build (`python misterzine.py build --with-repos` + `enrich-mra`):

| Export | What it is |
|---|---|
| `data/exports/arcade.json` | ~975 unique arcade titles, deduped across sources, with `year`, `manufacturer`, `rbf`, MiSTer `release_date`, `last_update`, source repo. ~450 have a real release date. |
| `data/exports/catalog.json` | Every current "release unit" across all 3 DBs (2,000+): arcade MRAs + console/computer/other cores. |
| `data/exports/arcade_release_history.json` | 156 arcade core repos with first-commit (debut) + last-commit dates — the raw retrospective timeline. |
| `data/exports/timeline.jsonl` | Append-only log of dated `new`/`updated`/`removed` events. Empty until the *second* run; fills as releases happen. |
| `data/misterzine.sqlite` | The database behind all of the above — query it directly for zine content. |

Example record (`arcade.json`):

```json
{
  "title": "Pac-Man - Puck Man (JP, Set 1)",
  "year": "1980", "manufacturer": "Namco", "rbf": "pacman",
  "release_date": "2017-11-09T05:49:26Z",
  "last_update": "2026-06-26T06:12:21Z",
  "repo": "MiSTer-devel/Arcade-Pacman_MiSTer"
}
```

## The three sources (all public, no betas)

1. **MiSTer Distribution** — `Distribution_MiSTer/db.json.zip` (official, all systems)
2. **JTcores (public)** — `jtcores_mister/jtbindb.json.zip` (Jotego's *free* cores; premium betas are excluded by default)
3. **Coin-Op Collection** — `Distribution-MiSTerFPGA` `db` branch (public arcade cores)

All three publish the same `{timestamp, files{path:{hash,size}}}` format, so one parser handles them.

Note: jtbindb also lists some cores that are still Patreon betas — their MRA ships
publicly but the core needs the `beta.bin` key, so they're effectively paywalled.
Jotego tags these `jtbeta` in the db's `tag_dictionary`; `fetch_db()` drops any
file carrying that tag (and purges rows ingested before the filter). When a core
graduates to free the tag is removed and it flows back in on its own.

## Why it's built this way (important)

The obvious plan — "diff the git history of `db.json.zip`" — **does not work**. All three DB
files are force-squashed (each lives in exactly **one** commit), and the Distribution repo
also wholesale-recommits its core files, so per-file git lineage is destroyed.

The **only** source of true historical MiSTer release dates is the **per-core GitHub repos**
(`MiSTer-devel/Arcade-*` for arcade, `MiSTer-devel/<core>_MiSTer` for console/computer/other).
Each repo's *first commit* is that core's MiSTer debut, and that history is intact going back
to 2017. So:

- **Retrospective dates** come from crawling those ~156 arcade repos (`repos` command) and the
  console/computer/other per-core repos (`core-repos` command).
- **The current catalog** comes from the 3 `db.json.zip` files (`snapshot` command).
- **Going-forward dates** come from snapshotting those DBs and diffing hashes over time.

> **Why `core-repos` matters:** console/computer/other cores ship as a single `.rbf` whose
> filename carries a `_YYYYMMDD` *build-date* suffix — **not** a debut date. An upstream mass
> rebuild restamps dozens of old cores with the same recent date (e.g. C64 looked like a
> 2026 release). `core-repos` replaces that with the real first-commit debut. The handful of
> cores whose repo doesn't follow the `<core>_MiSTer` naming (odd repo names, or no repo at all)
> are pinned in the hand-verified `CORE_FROZEN_DATES` table in `misterzine.py` — looked up once
> and frozen so they can never drift to look newly released. Every console/computer/other core
> now carries a real debut date (the `_YYYYMMDD` build-date suffix is only a last-resort fallback
> for a brand-new core not yet dated, shown greyed).

Jotego and Coin-Op keep their history elsewhere, and both are now backfilled too:

- **Jotego** (`jtcores` command): cores live in the `jotego/jtcores` monorepo under
  `cores/<name>/`. Each folder's first/last commit gives debut + last-update. Titles map via
  the MRA `<rbf>` (`jt<name>.rbf` → `cores/<name>`). Dated back to ~2019.
- **Coin-Op** (`coinop` command): its `develop` branch tags releases in commit messages
  (`"Snow Bros. Release 20260611"`), parsed straight into title + date. Back to 2024.

Current dated coverage: **~745 of ~975 unique arcade titles** (459 MiSTer-devel, 264 Jotego,
22 Coin-Op), spanning **2017 → today**.

### Known v1 limitations
- **~230 arcade titles remain undated** — mostly alt-region MRAs whose core didn't name-match,
  and a few oddly-named cores. They're fully catalogued and will get dates from the
  going-forward diff engine; they just lack a backfilled debut.
- `year`/`manufacturer` come from MRA XML for Distribution + Jotego (top-level MRAs); the few
  Coin-Op-exclusive titles lack year/manufacturer (dates only).
- Jotego enrichment uses the 266 top-level MRAs; deep `_alternatives/` variants are skipped.

## Commands

```bash
python misterzine.py build --with-repos   # full first run: snapshot + repo dates + export
python misterzine.py enrich-mra           # add year/manufacturer/rbf from MRA XML (run once, then occasionally)

# routine / scheduled:
python misterzine.py snapshot             # fetch DBs, diff vs last snapshot, log dated events
python misterzine.py export               # regenerate JSON/JSONL exports
python misterzine.py export-web           # regenerate the static site in docs/ (GitHub Pages)
python misterzine.py stats                # summary
python misterzine.py repos                # MiSTer-devel arcade release dates (occasional)
python misterzine.py core-repos           # console/computer/other core debut dates (occasional)
python misterzine.py jtcores              # Jotego release dates from jtcores monorepo
python misterzine.py coinop               # Coin-Op release dates from develop commit messages
python misterzine.py genre                # arcade genre from MAME catver.ini (joined on setname)
```

Typical first-time setup (full retrospective):
```bash
python misterzine.py build --with-repos   # snapshot + all four date backfills + export
python misterzine.py enrich-mra           # year/manufacturer/rbf/setname (also re-enables Jotego join)
python misterzine.py jtcores              # re-run so the rbf join now attaches Jotego dates
python misterzine.py genre                # arcade genre from catver.ini (needs setname from enrich-mra)
python misterzine.py export-web           # regenerate docs/ for the website
```
(`enrich-mra` must run before the Jotego join can match titles to cores by `rbf` *and* before
`genre` can match by `setname`, so on a cold start run `build --with-repos`, then `enrich-mra`,
then `jtcores` and `genre`.)

## The website (`docs/` → GitHub Pages)

`export-web` writes a self-contained static site under `docs/releases/` (served at
`/misterzine/releases/`); `docs/index.html` is just a redirect to it so the bare URL still works:
- `docs/releases/data.json` — one slim record per release unit (~2,010): `title`, `base`
  (Arcade/Console/Computer/Other), `genre`, `date`, `date_kind`, `year`, `manufacturer`.
- `docs/releases/index.html` — a single dependency-free page (vanilla JS) rendering a searchable,
  sortable, type-filterable table, **sorted most-recent-first by default**. The **Type** column
  reads `Arcade, <genre>` for arcade titles and `Console core` / `Computer core` / `Other core`
  for cores (a retired core reads `… core (deprecated)`). The **Date** column is the MiSTer debut
  where known, otherwise the core's latest build date (`_YYYYMMDD` suffix, greyed) — column titled
  **MiSTer release date**. Console and computer cores carry their hardware maker
  (Nintendo/Sega/Commodore/Sinclair/…) from the `CONSOLE_MANUFACTURER` / `COMPUTER_MANUFACTURER`
  maps, and the original hardware's release year (column **Original Year**) from the `CORE_YEAR`
  map (obscure/DIY makers and years web-verified). Every console/computer core has a year; a few
  modern/clone cores with no single vintage machine (`ao486`, `MultiComp`, `TSConf`) use a
  best-effort year (i486 era / their FPGA-design creation year).

The retired **Sega Genesis** core (replaced by MegaDrive — same console) is no longer in any DB,
so it's injected for the record via `EXTRA_WEB_ROWS`, dated from its archived repo.

Genre comes from MAME's **catver.ini** (fetched at build time, cached under `data/cache/`),
joined to each title by its MRA `<setname>`. ~708 arcade titles are genred; the rest
(Coin-Op titles with no MRA, and a few clone setnames) show a bare `Arcade`.

To publish: commit the repo, push to GitHub, and enable Pages on the `main` branch `/docs`
folder. Re-run `export-web` and push to update the live site.

## Going forward (keeping it up to date)

Run `python misterzine.py snapshot` on a schedule (daily is plenty — cores ship every few
days). Each run diffs the freshly-fetched DBs against the previous snapshot and appends
dated `new`/`updated` events to the `events` table and `timeline.jsonl`. Re-run `export`
after. Occasionally re-run `repos` to pick up brand-new arcade core repos.

On Windows, schedule with Task Scheduler, or use the Claude Code `/schedule` skill.

## Data model (`misterzine.sqlite`)

- `sources` — the 3 DBs and their last-seen timestamps.
- `catalog` — one row per (source, path) release unit: system, title, hash, year,
  manufacturer, rbf, repo, release_date, last_update, first_seen/last_seen/last_changed.
- `arcade_repos` — per-core arcade repo: first_commit, last_commit, commit count.
- `core_repos` — per-core console/computer/other repo (debut dates): first_commit, last_commit, commit count.
- `events` — dated change log (the going-forward feed).

## Layout

```
misterzine.py            # the tool (stdlib only; uses `gh` for an API token)
data/
  misterzine.sqlite      # the database
  snapshots/<source>/    # timestamped DB snapshots (diff inputs)
  repos/                 # sparse Distribution clone (for MRA metadata)
  exports/               # JSON/JSONL outputs for the zine
README.md
```
