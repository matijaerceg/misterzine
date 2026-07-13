<img width="3018" height="1536" alt="image" src="https://github.com/user-attachments/assets/edf30b93-c064-4800-b81f-01879e996c6e" />

# misterzine

An automated release database for **MiSTer FPGA** cores, and the public site it powers:

**[MiSTer FPGA Core & Arcade Tracker](https://misterzine.fyi/releases/)**,
a searchable, sortable index of every public MiSTer console, computer, and utility core
plus every public arcade title (1,000+ rows), with real debut dates back to **2017**,
shipped-update dates, screenshots, hardware photos, and RSS feeds. It refreshes itself
**four times a day** via GitHub Actions with no manual steps.

The database answers two questions:

- **Retrospective:** which titles exist, when did each core *debut* on MiSTer, and when
  was it last updated? (Real dates going back to 2017.)
- **Going forward:** what's *new or updated* since the last check, with a date stamp?

Everything the site shows is also available as plain JSON (see [Exports](#exports)).
User-visible site changes are logged in [CHANGELOG.md](CHANGELOG.md).

## The site (`docs/` → GitHub Pages)

A single dependency-free page (vanilla JS, self-hosted fonts, no trackers beyond a
privacy-friendly [GoatCounter](https://misterzine.goatcounter.com/) hit counter whose
dashboard is public, linked as "Traffic Stats" in the header).

**The table**
- One row per core or arcade title: 896 arcade, 69 computer, 44 console, 12 other
  (1,021 rows, all but a handful carrying a real dated debut).
- Sortable columns, multi-select Type filter, and **type-anywhere search**: stray
  keystrokes go straight into the search box. Search ignores accents.
- Default sort is **Last Updated**, newest first; the Title column stays pinned while
  scrolling horizontally; every column header explains itself on hover.
- **Type** reads `Arcade, <genre>` for arcade titles (genre from MAME's catver.ini) and
  `Console core` / `Computer core` / `Other core` for cores.
- **Core** links every row to its GitHub repository.
- Console/computer rows carry their hardware maker (Nintendo/Sega/Commodore/...) and the
  original hardware's release year (**Original Year**), from hand-verified maps in
  `misterzine.py`.
- **Opt-in columns** via the Columns dropdown: Genre, ROM Name (MAME setname), and the
  arcade metadata set (Resolution, Rotation, Players, Controls, Flip) from the curated
  [MiSTer Arcade Database](https://github.com/Toryalai1/MiSTer_ArcadeDatabase). Titles MAD
  hasn't catalogued yet show provisional gray values from mame2003-plus, replaced
  automatically once verified data lands.
- Arcade titles are written the way humans write them, from MAME's descriptions
  ("Pac-Man", "Street Fighter II: The World Warrior"), not raw MRA filenames; discarded
  alternate names stay searchable.

**The detail panel**
- Every row opens a panel: arcade titles show self-hosted native-resolution screenshots
  (title / snap / in-game, ~920 titles covered); console and computer cores show a photo
  of the actual hardware (127 systems, in a deliberately lo-fi 16-color dithered style).
- Three dates side by side: **MiSTer debut**, **Latest update** (newest shipped build),
  and **Latest commit** (repo activity).
- Click-to-copy ROM/core names, per-system notes, and a "Report a problem" link
  (prefilled GitHub issue).
- **Every entry has a shareable deep link** (e.g. `releases/#pacman` opens Pac-Man's
  panel); a 🔗 button copies it, and the browser Back gesture closes the panel on mobile.
- Esc closes, arrow keys walk rows, theme toggle: auto / light / dark.
- A **Launch button** that starts the game or core on your own MiSTer (see below).

### Launch on your MiSTer

Every launchable entry's panel has a "▶ Launch on MiSTer" button that starts it on real
hardware over your local network: arcade entries launch the actual game (the `.mra` must
be on your SD card), console/computer entries load the core.

Setup (once per browser):

1. On the MiSTer, install and run **Remote** from
   [MiSTer Extensions (mrext)](https://github.com/wizzomafizzo/mrext): available in
   `update_all` (MiSTer Extensions repo), then Scripts → `remote`. It starts a small web
   service on port 8182 and offers to keep itself running after reboots.
2. On the site, open any entry, click the Launch button, and add your MiSTer's address
   (hostname or IP; `mister.local` works on a stock setup, and the port defaults
   to 8182). Give it a name if you have several.
3. Click Launch. A tab flashes for a second while the request is handed to the MiSTer
   (a browser page can't quietly talk to a local device, so the brief tab *is* the
   request), then the game appears on your TV.

Notes:

- Multiple MiSTers are supported: the ▾ chevron next to the button adds, removes, and
  switches devices; picking one launches on it and makes it the new default.
- Device addresses live only in your browser's local storage; nothing is sent anywhere
  except to your own MiSTer, on your own network.
- Launching a game you don't have on the SD card fails politely: the flashed tab shows
  Remote's error text before closing.
- Console/computer launches need that core installed on the MiSTer. A brief
  "no core found" flash means it isn't: Remote checks the actual core files on every
  launch, and `http://<mister-ip>:8182/api/systems` lists exactly which systems are
  launchable on your device. Installing the core (e.g. via `update_all` with the main
  MiSTer distribution enabled) makes it work immediately, no rescan needed.
- Known limitation: if your cores come from the DB9/SNAC fork (an `update_all` option
  for DB9 controller support), console/computer launches will always fail with
  "no core found". Those builds use renamed core files (like
  `SNES_20260611_22baeda_DB9.rbf`) that Remote cannot match to a system, and there is
  no workaround short of also installing the official cores. Arcade launches are not
  affected.
- Works from a phone on the same wifi too.

**RSS feeds** (last 30 days / 100 items, autodiscoverable from the page or via the
header's "RSS" link; items deep-link to the entry on the site):
- `docs/releases/feed.xml`: all changes (new + updated)
- `docs/releases/feed-new.xml`: new cores & games only
- `docs/releases/feed-updates.xml`: shipped updates only

### Date semantics (the part people get wrong)

- **MiSTer Debut** is when the core first appeared on MiSTer: the first commit of its
  per-core GitHub repo, hand-verified where repo history lies. A brand-new core not yet
  dated falls back to its `_YYYYMMDD` filename build date, shown grayed.
- **Last Updated** is the newest **shipped build**: the dated file `update_all` actually
  delivers (filename suffix for cores, the referenced core `.rbf`'s date for arcade
  rows). It is deliberately *not* the repo's latest commit, which often lands before or
  without a shipped build; that shows separately in the panel as "Latest commit".

## How it stays fresh

`.github/workflows/update.yml` runs **four times a day** (00/06/12/18 UTC at :12):

1. `snapshot`: fetch the three upstream DBs, diff against the last snapshot, log dated
   `new`/`updated`/`removed` events.
2. `enrich-mra`: year/manufacturer/rbf/setname for any new arcade titles.
3. `repos` / `core-repos` / `jtcores` / `coinop`: incremental repo crawls for debut and
   last-update dates. Each crawl skips every repo not pushed since its last crawl, so a
   typical day costs a handful of API calls (non-fatal on hiccups).
4. `genre`, `mad`, `specs`: refresh genre, arcade metadata, and provisional specs.
5. `export` + `export-web`: regenerate the JSON exports and the static site.
6. Commit and push only if the published outputs actually changed (a quiet run publishes
   nothing). Pages serves `main /docs`, so the push *is* the deploy.

New arcade titles even get screenshots auto-backfilled from libretro-thumbnails on the
daily run; the higher-quality progettoSNAPS pass is a manual local step (see
[Images](#the-image-pipeline-tools)).

## The three sources (all public, no betas)

1. **MiSTer Distribution**: `Distribution_MiSTer/db.json.zip` (official, all systems)
2. **JTcores (public)**: `jtcores_mister/jtbindb.json.zip` (Jotego's *free* cores)
3. **Coin-Op Collection**: `Distribution-MiSTerFPGA` `db` branch (public arcade cores)

All three publish the same `{timestamp, files{path:{hash,size}}}` format, so one parser
handles them.

Note: jtbindb also lists cores that are still Patreon betas; their MRA ships publicly but
the core needs the `beta.bin` key, so they're effectively paywalled. Jotego tags these
`jtbeta` in the db's `tag_dictionary`; `fetch_db()` drops any file carrying that tag (and
purges rows ingested before the filter existed). When a core graduates to free, the tag
is removed upstream and it flows back in on its own.

## Why it's built this way (important)

The obvious plan, "diff the git history of `db.json.zip`", **does not work**. All three
DB files are force-squashed (each lives in exactly one commit), and the Distribution repo
also wholesale-recommits its core files, so per-file git lineage is destroyed.

The **only** source of true historical MiSTer release dates is the **per-core GitHub
repos** (`MiSTer-devel/Arcade-*` for arcade, `MiSTer-devel/<core>_MiSTer` for
console/computer/other). Each repo's *first commit* is that core's MiSTer debut, and that
history is intact going back to 2017. So:

- **Retrospective dates** come from crawling those ~160 arcade repos (`repos` command)
  and the console/computer/other per-core repos (`core-repos` command).
- **The current catalog** comes from the 3 `db.json.zip` files (`snapshot` command).
- **Going-forward dates** come from snapshotting those DBs and diffing hashes over time.

> **Why `core-repos` matters:** console/computer/other cores ship as a single `.rbf`
> whose filename carries a `_YYYYMMDD` *build-date* suffix, **not** a debut date. An
> upstream mass rebuild restamps dozens of old cores with the same recent date (e.g. C64
> once looked like a 2026 release). `core-repos` replaces that with the real first-commit
> debut. Cores whose repo doesn't follow the `<core>_MiSTer` naming (odd repo names, or
> no repo at all) are pinned in the hand-verified `CORE_FROZEN_DATES` table in
> `misterzine.py`: looked up once and frozen so they can never drift to look newly
> released. The same principle applies everywhere: displayed dates never inflate to make
> old items look new (Jotego's Feb-2023 monorepo migration and wave rebuilds that touch
> every `.rbf` are both filtered out).

Jotego and Coin-Op keep their history elsewhere, and both are backfilled too:

- **Jotego** (`jtcores` command): cores live in the `jotego/jtcores` monorepo under
  `cores/<name>/`. Each folder's first/last commit gives debut + last-update. Titles map
  via the MRA `<rbf>` (`jt<name>.rbf` → `cores/<name>`). Dated back to ~2019.
- **Coin-Op** (`coinop` command): its `develop` branch tags releases in commit messages
  (`"Snow Bros. Release 20260611"`), parsed straight into title + date. Back to 2024.

Current dated coverage: **999 arcade titles** carry a real debut date (529 via
MiSTer-devel repos, 253 Jotego, 144 Coin-Op, the rest hand-verified), spanning
**2017 → today**. Every console/computer/other core has a real debut date too.

### Known rough edges
- A few MRAs share one MAME setname across genuinely different games (e.g. the `btime`
  conversions), so those rows can't be fully disambiguated for titles/screenshots.
- Jotego enrichment uses the top-level MRAs; deep `_alternatives/` variants are skipped.

## Commands

```bash
python misterzine.py snapshot     # fetch DBs, diff vs last snapshot, log dated events
python misterzine.py enrich-mra   # add year/manufacturer/rbf/setname from MRA XML
python misterzine.py repos        # MiSTer-devel arcade repo dates (incremental)
python misterzine.py core-repos   # console/computer/other core debut dates (incremental)
python misterzine.py jtcores      # Jotego dates from the jtcores monorepo (incremental)
python misterzine.py coinop       # Coin-Op dates from develop commit messages
python misterzine.py genre        # arcade genre from MAME catver.ini (joined on setname)
python misterzine.py mad          # arcade rotation/resolution/players/controls from MAD
python misterzine.py specs        # provisional specs (mame2003-plus) for rows not in MAD
python misterzine.py mame-meta    # derive committed mame_meta.json.gz from the raw MAME DAT (local pass)
python misterzine.py export       # write JSON/JSONL exports from the db
python misterzine.py export-web   # write the static site (docs/) for GitHub Pages
python misterzine.py stats        # database summary
python misterzine.py build        # snapshot + export + stats (--with-repos adds all date backfills)
```

Cold-start setup (full retrospective from an empty `data/`):

```bash
python misterzine.py build --with-repos   # snapshot + all four date backfills + export
python misterzine.py enrich-mra           # year/manufacturer/rbf/setname
python misterzine.py jtcores              # re-run: the rbf join can now attach Jotego dates
python misterzine.py genre                # needs setname from enrich-mra
python misterzine.py mad
python misterzine.py specs
python misterzine.py export-web
```

(`enrich-mra` must run before the Jotego join can match titles by `rbf` and before
`genre`/`mad`/`specs` can match by `setname`, hence the ordering.)

## Exports

| Export | What it is |
|---|---|
| `data/exports/arcade.json` | ~1,000 unique arcade titles, deduped across sources, with `year`, `manufacturer`, `rbf`, `setname`, `genre`, MiSTer `release_date`, `last_update`, source repo. |
| `data/exports/catalog.json` | Every current "release unit" across all 3 DBs (~2,000): arcade MRAs (including alternatives) + console/computer/other cores. |
| `data/exports/arcade_release_history.json` | ~160 arcade core repos with first-commit (debut) + last-commit dates: the raw retrospective timeline. |
| `data/exports/timeline.jsonl` | Append-only log of dated `new`/`updated`/`removed` events. |
| `data/misterzine.sqlite` | The database behind all of the above; query it directly. |

Example record (`arcade.json`):

```json
{
  "title": "Eeek! (Pac-Man Conversion)",
  "year": "1984", "manufacturer": "Epos Corporation",
  "rbf": "pacman", "setname": "eeekkp", "genre": "Platform",
  "release_date": "2017-11-09T05:49:26Z",
  "last_update": "2026-06-26T06:12:21Z",
  "repo": "MiSTer-devel/Arcade-Pacman_MiSTer"
}
```

## The image pipeline (`tools/`)

Arcade screenshots are self-hosted at native resolution under
`docs/images/{title,snap,ingame}/`, keyed by MAME setname:

- `tools/build_manifest.py`: resolve title + snap + one in-game shot per arcade title,
  deterministically against [progettoSNAPS](https://www.progettosnaps.net/) packs, using
  the MAME DAT's `cloneof` to fall back to the parent set; libretro-thumbnails
  display-name matching backfills titles with no setname.
- `tools/fetch_images.py`: download and extract only the needed PNGs.
- `tools/fetch_system_photos.py`: console/computer hardware photos from Wikimedia
  Commons for `docs/images/systems/` (background-removed, alpha-trimmed, scaled to
  164px; full color).
- `docs/mask.js`: the CRT shadow-mask effect drawn over screenshots and hardware
  photos in the browser is the slot mask from Timothy Lottes' RVM (Retro Video
  Monitor) shader, released into the public domain under the Unlicense; ported here
  to canvas and rendered at the viewer's native device pixels.
- `data/cache/image_manifest.json` (committed) ties images to rows and records misses so
  runs don't re-resolve them.

The daily CI job auto-fetches libretro shots for brand-new titles (progettoSNAPS can't
run on Actions); the native-res progettoSNAPS pass stays a manual local step.

## Data model (`misterzine.sqlite`)

- `sources`: the 3 DBs and their last-seen timestamps.
- `catalog`: one row per (source, path) release unit: system, title, hash, year,
  manufacturer, rbf, setname, genre, repo, release_date, last_update,
  first_seen/last_seen/last_changed.
- `arcade_repos` / `core_repos`: per-core repo crawl results (first_commit = debut,
  last_commit, commit count).
- `jt_cores` / `coinop_releases`: the Jotego and Coin-Op date backfills.
- `core_files`: dated shipped files per core, harvested at snapshot (feeds the site's
  Last Updated column).
- `events`: dated change log (the going-forward feed; feeds the RSS).

## Layout

```
misterzine.py            # the tool (stdlib only; uses `gh` or GH_TOKEN for the API)
.github/workflows/
  update.yml             # the 4x-daily refresh + publish job
tools/                   # image pipeline (manifest build, fetchers, matching)
data/
  misterzine.sqlite      # the database (committed)
  exports/               # JSON/JSONL outputs (committed)
  cache/                 # gitignored except: image_manifest.json,
                         #   ArcadeDatabase.csv (MAD fallback),
                         #   mame_meta.json.gz, mame2003_specs.json.gz
                         #   (committed so CI builds match local ones)
  snapshots/<source>/    # timestamped DB snapshots (diff inputs; gitignored)
  repos/                 # sparse Distribution clone for MRA metadata (gitignored)
docs/                    # the site, served by GitHub Pages from main /docs
  index.html             # redirect to /releases/
  fonts/  images/        # self-hosted Roboto + all screenshots/photos
  releases/
    index.html           # the app (single file, vanilla JS)
    data.json            # one slim record per row
    meta.json            # build stamp (staleness checks)
    feed*.xml            # the three RSS feeds
CHANGELOG.md             # user-visible site changes
```
