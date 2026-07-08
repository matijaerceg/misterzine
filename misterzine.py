#!/usr/bin/env python3
"""
misterzine - a release database for MiSTer FPGA cores (arcade-focused).

Builds and maintains a local database of MiSTer releases from three angles:

  1. catalog  - the *current* set of titles across the three public DBs
                (MiSTer Distribution, JTcores public, Coin-Op Collection).
  2. repos    - the *retrospective* real release dates, mined from the
                per-core GitHub repos (MiSTer-devel/Arcade-*), whose first
                commit == the core's MiSTer debut (history goes back years).
  3. snapshot - the *going-forward* engine: snapshots each DB and diffs hashes
                against the previous snapshot to log dated new/updated events.

Why this shape: the db.json.zip files themselves are force-squashed (1 commit),
so their git history is useless for backfill. The per-core repos are the only
source of true historical MiSTer release dates.  See README.md.

Stdlib only. Uses the `gh` CLI just to borrow an auth token for the GitHub API.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SNAPDIR = DATA / "snapshots"
EXPORTDIR = DATA / "exports"
CACHEDIR = DATA / "cache"
DBPATH = DATA / "misterzine.sqlite"
DOCSDIR = ROOT / "docs"

# --- Sources --------------------------------------------------------------

SOURCES = [
    {
        "id": "distribution_mister",
        "name": "MiSTer Distribution",
        "db_url": "https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip",
    },
    {
        "id": "jtbindb",
        "name": "JTcores (public)",
        "db_url": "https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip",
    },
    {
        "id": "coinop",
        "name": "Coin-Op Collection",
        "db_url": "https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip",
    },
]

# GitHub org + name prefix where the retrospective arcade release dates live.
ARCADE_REPO_ORG = "MiSTer-devel"
ARCADE_REPO_PREFIX = "Arcade-"

UA = "misterzine/0.1 (+https://github.com/MiSTer-devel)"


# --- small helpers --------------------------------------------------------

def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def iso_z(s):
    """Normalize an ISO-8601 UTC timestamp to the trailing-Z form so values
    from GitHub (…Z) and now_iso() (…+00:00) compare lexically."""
    return (s or "").replace("+00:00", "Z")


def epoch_to_iso(ts):
    try:
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def log(*a):
    print(*a, file=sys.stderr, flush=True)


_token_cache = None


def gh_token():
    global _token_cache
    if _token_cache is None:
        # Prefer an env token (GitHub Actions sets GITHUB_TOKEN; we also honour
        # GH_TOKEN) so the pipeline authenticates in CI without `gh auth login`.
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        if not tok:
            try:
                tok = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
            except Exception:
                tok = ""
        _token_cache = tok
    return _token_cache


def http_get(url, headers=None, want_headers=False, retries=3):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                if want_headers:
                    return body, dict(r.headers)
                return body
        except urllib.error.HTTPError as e:
            last = e
            # respect secondary rate limit / abuse
            if e.code in (403, 429):
                wait = 2 ** attempt * 3
                log(f"  rate-limited ({e.code}), sleeping {wait}s")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise last


def gh_api(path, want_headers=False):
    url = "https://api.github.com" + path if path.startswith("/") else path
    headers = {"Accept": "application/vnd.github+json"}
    tok = gh_token()
    if tok:
        headers["Authorization"] = "Bearer " + tok
    body, hdrs = http_get(url, headers=headers, want_headers=True)
    data = json.loads(body) if body else None
    return (data, hdrs) if want_headers else data


# --- DB layer -------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, name TEXT, db_url TEXT,
    last_timestamp INTEGER, last_timestamp_iso TEXT, last_fetch TEXT
);
CREATE TABLE IF NOT EXISTS catalog (
    source_id TEXT, path TEXT, system TEXT, kind TEXT, title TEXT,
    hash TEXT, size INTEGER,
    year TEXT, manufacturer TEXT, rbf TEXT, setname TEXT, genre TEXT,
    repo TEXT, release_date TEXT, last_update TEXT,
    first_seen TEXT, last_seen TEXT, last_changed TEXT,
    PRIMARY KEY (source_id, path)
);
CREATE TABLE IF NOT EXISTS arcade_repos (
    repo TEXT PRIMARY KEY, core TEXT, html_url TEXT,
    first_commit TEXT, last_commit TEXT, commits INTEGER, crawled_at TEXT
);
CREATE TABLE IF NOT EXISTS core_repos (
    repo TEXT PRIMARY KEY, core TEXT, html_url TEXT,
    first_commit TEXT, last_commit TEXT, commits INTEGER, crawled_at TEXT
);
CREATE TABLE IF NOT EXISTS jt_cores (
    folder TEXT PRIMARY KEY, rbf TEXT,
    first_commit TEXT, last_commit TEXT, commits INTEGER, crawled_at TEXT
);
CREATE TABLE IF NOT EXISTS coinop_releases (
    title TEXT PRIMARY KEY, release_date TEXT, commit_date TEXT
);
CREATE TABLE IF NOT EXISTS events (
    ts TEXT, source_id TEXT, path TEXT, title TEXT, system TEXT,
    event_type TEXT, hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_catalog_title ON catalog(title);
"""


def _ensure_columns(con):
    """Add columns introduced after the original schema to a pre-existing DB.

    CREATE TABLE IF NOT EXISTS won't alter an already-created table, so add new
    columns idempotently (the ALTER no-ops/raises if the column already exists).
    """
    for col, decl in [("setname", "TEXT"), ("genre", "TEXT")]:
        try:
            con.execute(f"ALTER TABLE catalog ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass  # column already present


def connect():
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DBPATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _ensure_columns(con)
    return con


# --- classification -------------------------------------------------------

def classify(path):
    """Return (system, kind, is_release_unit) for a db file path."""
    p = path.replace("\\", "/")
    low = p.lower()
    if low.startswith("_arcade/") and low.endswith(".mra"):
        return "arcade", "title", True
    if low.startswith("_arcade/"):
        return "arcade", "support", False  # cores/, mra alts, hbmame, etc.
    if low.startswith("_console/") and low.endswith(".rbf"):
        return "console", "core", True
    if low.startswith("_computer/") and low.endswith(".rbf"):
        return "computer", "core", True
    if low.startswith("_other/") and low.endswith(".rbf"):
        return "other", "core", True
    if low.startswith("_console/"):
        return "console", "support", False
    if low.startswith("_computer/"):
        return "computer", "support", False
    return "support", "support", False


def title_from_path(path):
    stem = Path(path.replace("\\", "/")).name
    for ext in (".mra", ".rbf"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    return stem


def norm_key(title):
    """Loose normalized key for joining titles across sources / to repos."""
    t = title.lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", "", t)        # drop (World ...) [hash] etc.
    t = re.sub(r"[^a-z0-9]+", "", t)
    return t


# --- fetch + normalize ----------------------------------------------------

def fetch_db(source):
    """Download a db.json.zip, return (timestamp, {path: {hash,size}}, [beta_paths]).

    Jotego marks Patreon-only cores with the 'jtbeta' tag in the db's
    tag_dictionary: the MRA ships in the public db but the core requires the
    beta.bin key (a Patreon reward), so it's effectively paywalled. The site is
    public-only, so we drop those files here and return their paths so the caller
    can purge any rows ingested before this filter existed. When such a core
    later graduates to free, Jotego removes the tag and it flows back in with its
    real (graduation-day) debut date — no manual list to maintain."""
    log(f"  fetching {source['name']} ...")
    raw = http_get(source["db_url"])
    z = zipfile.ZipFile(BytesIO(raw))
    inner = z.read(z.namelist()[0])
    d = json.loads(inner)
    beta_tag = d.get("tag_dictionary", {}).get("jtbeta")
    files = {}
    beta_paths = []
    for path, meta in d.get("files", {}).items():
        if beta_tag is not None and beta_tag in meta.get("tags", []):
            beta_paths.append(path)
            continue
        files[path] = {"hash": meta.get("hash"), "size": meta.get("size")}
    if beta_paths:
        log(f"    excluded {len(beta_paths)} jtbeta (Patreon-gated) files")
    return d.get("timestamp"), files, beta_paths


def latest_snapshot(source_id):
    sd = SNAPDIR / source_id
    if not sd.exists():
        return None
    snaps = sorted(sd.glob("*.json"))
    if not snaps:
        return None
    return json.loads(snaps[-1].read_text(encoding="utf-8"))


def catalog_files(con, source_id):
    """Reconstruct the previous {path: {'hash': ...}} baseline from the committed
    catalog table. Used when no snapshot file is present — e.g. a fresh checkout
    on CI, where data/snapshots/ is gitignored but the sqlite (which carries the
    last-seen hash per path) IS committed. Without this the diff engine would see
    no prior state, re-seed every run, and never log a going-forward event."""
    rows = con.execute(
        "SELECT path, hash FROM catalog WHERE source_id=?", (source_id,)
    ).fetchall()
    return {r["path"]: {"hash": r["hash"]} for r in rows}


def write_snapshot(source_id, timestamp, files):
    sd = SNAPDIR / source_id
    sd.mkdir(parents=True, exist_ok=True)
    stamp = str(int(timestamp) if timestamp else int(time.time()))
    path = sd / f"{stamp}.json"
    path.write_text(json.dumps({"timestamp": timestamp, "files": files}), encoding="utf-8")
    return path


# --- command: snapshot (going-forward diff engine) ------------------------

def cmd_snapshot(args):
    con = connect()
    total_events = 0
    for source in SOURCES:
        ts, files, beta_paths = fetch_db(source)
        prev = latest_snapshot(source["id"])
        ts_iso = epoch_to_iso(ts) or now_iso()

        # Purge any Patreon-gated (jtbeta) rows that were ingested before the
        # fetch_db filter existed. These were never legitimately public, so we
        # delete the catalog rows outright rather than leaving stale entries the
        # export would keep serving forever (SELECT * FROM catalog).
        beta_set = set(beta_paths)
        for path in beta_paths:
            con.execute("DELETE FROM catalog WHERE source_id=? AND path=?",
                        (source["id"], path))

        con.execute(
            "INSERT INTO sources(id,name,db_url,last_timestamp,last_timestamp_iso,last_fetch) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "last_timestamp=excluded.last_timestamp, last_timestamp_iso=excluded.last_timestamp_iso, "
            "last_fetch=excluded.last_fetch",
            (source["id"], source["name"], source["db_url"], ts, ts_iso, now_iso()),
        )

        if prev is not None:
            old_files = prev["files"]
            seed = False
        else:
            # No snapshot file on disk (fresh CI checkout — snapshots/ is
            # gitignored). Fall back to the committed catalog table so the diff
            # still works; only a genuinely empty catalog is a true first seed.
            old_files = catalog_files(con, source["id"])
            seed = not old_files
        events = []

        for path, meta in files.items():
            system, kind, is_unit = classify(path)
            if not is_unit:
                continue
            old = old_files.get(path)
            if old is None:
                etype = "seed" if seed else "new"
            elif old.get("hash") != meta.get("hash"):
                etype = "updated"
            else:
                etype = None
            if etype:
                events.append((ts_iso, source["id"], path, title_from_path(path), system, etype, meta.get("hash")))

        # removals (only meaningful after seed). Skip jtbeta paths: they're being
        # purged as never-legitimately-public, not organically removed upstream,
        # so a "removed" event would misrepresent the history.
        if not seed:
            for path in old_files:
                if path not in files and path not in beta_set:
                    system, kind, is_unit = classify(path)
                    if not is_unit:
                        continue
                    events.append((ts_iso, source["id"], path, title_from_path(path), system, "removed", None))

        # upsert catalog rows for everything currently present
        upsert_catalog(con, source["id"], files, ts_iso, seed)

        # A core rebuild renames its rbf (PDP1_20190101.rbf -> PDP1_20260702.rbf),
        # which the diff sees as new+removed and upsert_catalog as a brand-new row
        # — leaving the stale row behind (the export SELECTs the whole catalog, so
        # the site would show the core twice) and stamping today as the new row's
        # release_date (recency inflation). Treat it as a rename instead: carry
        # the old row's debut/first_seen onto the new row, then drop the old row.
        if not seed:
            current = {}
            for path in files:
                system, kind, is_unit = classify(path)
                if is_unit and kind == "core":
                    current.setdefault((system, core_name(title_from_path(path))), path)
            for path in old_files:
                if path in files or path in beta_set:
                    continue
                system, kind, is_unit = classify(path)
                if not (is_unit and kind == "core"):
                    continue
                new_path = current.get((system, core_name(title_from_path(path))))
                old_row = con.execute(
                    "SELECT release_date, first_seen FROM catalog WHERE source_id=? AND path=?",
                    (source["id"], path)).fetchone()
                if new_path and old_row:
                    # release_date is copied verbatim (even NULL: an undated old
                    # row means the true debut is unknown, not "today")
                    con.execute(
                        "UPDATE catalog SET release_date=?, first_seen=? WHERE source_id=? AND path=?",
                        (old_row["release_date"], old_row["first_seen"], source["id"], new_path))
                    con.execute("DELETE FROM catalog WHERE source_id=? AND path=?",
                                (source["id"], path))

        if not seed:
            con.executemany(
                "INSERT INTO events(ts,source_id,path,title,system,event_type,hash) VALUES(?,?,?,?,?,?,?)",
                events,
            )
        write_snapshot(source["id"], ts, files)
        kind_counts = {}
        for e in events:
            kind_counts[e[5]] = kind_counts.get(e[5], 0) + 1
        log(f"  {source['name']}: {'SEED' if seed else 'diff'} -> {kind_counts or 'no changes'}")
        total_events += 0 if seed else len(events)

    con.commit()
    con.close()
    log(f"snapshot done. {total_events} new dated events logged.")


def upsert_catalog(con, source_id, files, ts_iso, seed):
    for path, meta in files.items():
        system, kind, is_unit = classify(path)
        if not is_unit:
            continue
        title = title_from_path(path)
        row = con.execute(
            "SELECT hash, first_seen FROM catalog WHERE source_id=? AND path=?",
            (source_id, path),
        ).fetchone()
        if row is None:
            # A title first seen via the going-forward diff (not the initial
            # seed) is genuinely debuting now, so its detection time IS its real
            # MiSTer release date — stamp it. Seed-time inserts leave it NULL so
            # the retrospective repo crawls supply the true historical debut and
            # old undated titles are never inflated to the cold-build date.
            release_date = None if seed else ts_iso
            con.execute(
                "INSERT INTO catalog(source_id,path,system,kind,title,hash,size,release_date,first_seen,last_seen,last_changed) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (source_id, path, system, kind, title, meta.get("hash"), meta.get("size"),
                 release_date, ts_iso, ts_iso, ts_iso),
            )
        else:
            changed = row["hash"] != meta.get("hash")
            con.execute(
                "UPDATE catalog SET hash=?, size=?, system=?, kind=?, title=?, last_seen=?, "
                "last_changed=CASE WHEN ? THEN ? ELSE last_changed END WHERE source_id=? AND path=?",
                (meta.get("hash"), meta.get("size"), system, kind, title, ts_iso,
                 changed, ts_iso, source_id, path),
            )


# --- command: repos (retrospective release dates) -------------------------

_org_repos_cache = None


def list_org_repos():
    """All public repos in ARCADE_REPO_ORG, keyed by lowercased name (GitHub
    repo lookups are case-insensitive; some repos vary the _MiSTer suffix case).
    One paginated listing serves both the arcade and console/computer crawls,
    and each repo object's pushed_at lets them skip repos untouched since the
    last crawl."""
    global _org_repos_cache
    if _org_repos_cache is not None:
        return _org_repos_cache
    repos = {}
    page = 1
    while True:
        data, hdrs = gh_api(
            f"/orgs/{ARCADE_REPO_ORG}/repos?per_page=100&page={page}&type=public", want_headers=True
        )
        if not data:
            break
        for r in data:
            repos[r["name"].lower()] = r
        link = hdrs.get("Link", "")
        if 'rel="next"' not in link:
            break
        page += 1
    _org_repos_cache = repos
    return repos


def list_arcade_repos():
    return [
        r for r in list_org_repos().values()
        if r["name"].startswith(ARCADE_REPO_PREFIX) and not r.get("archived", False)
    ]


def repo_commit_bounds(full_name, path=None):
    """Return (first_commit_iso, last_commit_iso, commit_count) using the Link trick.

    Optionally scope to a path (e.g. a core's folder in a monorepo).
    """
    suffix = f"&path={path}" if path else ""
    data, hdrs = gh_api(f"/repos/{full_name}/commits?per_page=1{suffix}", want_headers=True)
    if not data:
        return None, None, 0
    last_iso = data[0]["commit"]["committer"]["date"]
    # find last page number from Link header
    link = hdrs.get("Link", "")
    m = re.search(r'[?&]page=(\d+)[^>]*>;\s*rel="last"', link)
    count = int(m.group(1)) if m else 1
    if count <= 1:
        return last_iso, last_iso, 1
    oldest = gh_api(f"/repos/{full_name}/commits?per_page=1&page={count}{suffix}")
    first_iso = oldest[0]["commit"]["committer"]["date"] if oldest else last_iso
    return first_iso, last_iso, count


def cmd_repos(args):
    con = connect()
    log("listing arcade core repos ...")
    repos = list_arcade_repos()
    log(f"  found {len(repos)} {ARCADE_REPO_PREFIX}* repos")
    if args.limit:
        repos = repos[: args.limit]
    crawled = {
        r["repo"]: r["crawled_at"]
        for r in con.execute("SELECT repo, crawled_at FROM arcade_repos").fetchall()
    }
    skipped = 0
    for i, r in enumerate(repos, 1):
        full = r["full_name"]
        # incremental: a repo's first/last commit can't change without a push,
        # so skip anything not pushed since we last crawled it (--force overrides)
        prev = crawled.get(full)
        if prev and not getattr(args, "force", False) and iso_z(r.get("pushed_at")) <= iso_z(prev):
            skipped += 1
            continue
        try:
            first, last, count = repo_commit_bounds(full)
        except Exception as e:
            log(f"  [{i}/{len(repos)}] {full}: ERROR {e}")
            continue
        core = r["name"].replace("_MiSTer", "")
        con.execute(
            "INSERT INTO arcade_repos(repo,core,html_url,first_commit,last_commit,commits,crawled_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(repo) DO UPDATE SET "
            "first_commit=excluded.first_commit, last_commit=excluded.last_commit, "
            "commits=excluded.commits, crawled_at=excluded.crawled_at",
            (full, core, r["html_url"], first, last, count, now_iso()),
        )
        if i % 20 == 0 or i == len(repos):
            con.commit()
            log(f"  [{i}/{len(repos)}] {full}  debut={first[:10] if first else '?'}  updated={last[:10] if last else '?'}")
    if skipped:
        log(f"  skipped {skipped} repos unchanged since last crawl")
    con.commit()
    join_repos_to_catalog(con)
    apply_frozen_arcade_core_dates(con)
    con.commit()
    con.close()
    log("repos crawl done.")


# MRA <rbf> core names that don't normalize to their repo's core name
# (abbreviations/spelling differences). Maps normalized <rbf> -> normalized repo
# core name. The _MiSTer-suffix case bug is handled by _repo_key, not here.
ARCADE_RBF_ALIASES = {
    "taitosj": "taitosystemsj",   # Arcade-TaitoSystemSJ
    "atarisys1": "atarisystem1",  # Arcade-Atari-system1
    "sdgundamps": "gundamsd",     # Arcade-GundamSD
    "ataritetris": "atetris",     # Arcade-ATetris
    "rshnatk": "rushnattack",     # Arcade-RushnAttack
}


def _repo_key(name):
    """Normalized join key for a repo core name, tolerant of a trailing _MiSTer
    suffix that appears as _MISTer/_Mister in some repos and slips past a
    case-sensitive strip (e.g. Arcade-Arkanoid_MISTer)."""
    k = norm_key(name)
    if k.endswith("mister"):
        k = k[: -len("mister")]
    return k


def join_repos_to_catalog(con):
    """Attach repo release dates to arcade catalog rows.

    Match priority: the MRA <rbf> core name (most reliable), then the title.
    """
    repos = con.execute("SELECT repo, core, first_commit, last_commit FROM arcade_repos").fetchall()
    by_key = {}
    for r in repos:
        key = _repo_key(r["core"].replace("Arcade-", ""))
        by_key.setdefault(key, r)  # first wins
    n = 0
    for row in con.execute(
        "SELECT source_id, path, title, rbf FROM catalog WHERE system='arcade'"
    ).fetchall():
        r = None
        if row["rbf"]:
            rk = norm_key(row["rbf"])
            r = by_key.get(rk) or by_key.get(ARCADE_RBF_ALIASES.get(rk, ""))
        if r is None:
            r = by_key.get(_repo_key(row["title"]))
        if r:
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (r["repo"], r["first_commit"], r["last_commit"], row["source_id"], row["path"]),
            )
            n += 1
    log(f"  joined {n} arcade titles to a core repo (release dates attached)")


# Multi-game arcade cores that have NO per-core repo to date from (so the rbf
# join above can't reach them). Every title on the core debuts when the core
# does, so we pin one known public-availability date per <rbf>. Keyed by the
# normalized <rbf>. Dates are hand-verified (MiSTer forums / RetroRGB / repo).
ARCADE_CORE_FROZEN_DATES = {
    "stv":        "2025-02-14",  # Sega ST-V (Titan) — public in Saturn core Feb 2025
    "sms":        "2021-08-30",  # Sega System E arcade support added to SMS core
    "skysmasher": "2026-05-01",  # rmonic79 Arcade_SkySmasher v1.0, May 2026
    "jtngp":      "2024-06-16",  # Jotego NeoGeo Pocket core
}


def apply_frozen_arcade_core_dates(con):
    """Date repo-less multi-game arcade cores from ARCADE_CORE_FROZEN_DATES.

    Only fills rows still missing a date, keyed by the normalized <rbf>, so it
    never overrides a date a real repo/Coin-Op match already supplied.
    """
    n = 0
    for row in con.execute(
        "SELECT source_id, path, rbf FROM catalog "
        "WHERE system='arcade' AND rbf IS NOT NULL AND release_date IS NULL"
    ).fetchall():
        d = ARCADE_CORE_FROZEN_DATES.get(norm_key(row["rbf"]))
        if d:
            con.execute(
                "UPDATE catalog SET release_date=? WHERE source_id=? AND path=?",
                (d, row["source_id"], row["path"]),
            )
            n += 1
    if n:
        log(f"  pinned {n} titles on repo-less cores to a frozen debut date")


# --- command: core-repos (debut dates for console/computer/other cores) ---

# Hand-mapped overrides where the catalog core name doesn't equal the repo base
# name (repo = MiSTer-devel/<base>_MiSTer). Add entries here as misses surface.
CORE_REPO_OVERRIDES = {
    # "CatalogCoreName": "RepoBaseName",
    "GBA2P": "GBA",            # 2-player variant ships from the base core repo
    "GameGear2P": "SMS",       # Game Gear lives in the SMS core
    "Gameboy2P": "Gameboy",
    "Minimig": "Minimig-AGA",  # Amiga
    "Ti994a": "TI-99_4A",
    "RX78": "RX-78",
    "GameOfLife": "Life",
}

# Hand-verified MiSTer debut dates for cores the repo crawl can't reach via the
# `<core>_MiSTer` convention (repos under odd names, or no repo at all). These are
# FROZEN: each is the first-commit date of the core's real repo (or, for NeoGeo
# Pocket, its public beta release), looked up once and pinned so the displayed
# date never drifts as upstream rebuilds the core. Source repo noted per line.
CORE_FROZEN_DATES = {
    "SAMCoupe":      "2017-06-13",  # MiSTer-devel/SAM-Coupe_MiSTer first commit
    "Intellivision": "2019-09-02",  # MiSTer-devel/Intv_MiSTer first commit
    "AY-3-8500":     "2020-01-04",  # MiSTer-devel/AY-3-8500-MiSTer first commit
    "EpochGalaxyII": "2020-07-28",  # MiSTer-devel/EpochGalaxy2_MiSTer first commit
    "Ondra_SPO186":  "2021-10-18",  # MiSTer-devel/OndraSPO186_MiSTer first commit
    "Homelab":       "2022-12-15",  # MiSTer-devel/Homelab-MiSTer first commit
    "NeoGeoPocket":  "2024-01-05",  # public beta release (Time Extension/RetroRGB)
    "SCV":           "2024-07-24",  # MiSTer-devel/SuperCassetteVision_MiSTer first commit
    "Atari5200":     "2017-10-08",  # ships from the Atari800 core (Atari800_MiSTer debut)

    # --- corrections: repos exist & are crawled, but the first-commit date is
    # wrong because the repo carries imported/WIP/pre-MiSTer history, was forked
    # from another core, or prunes old releases. The value below is the build-date
    # suffix of the EARLIEST surviving `<core>_YYYYMMDD.rbf` in the repo's git
    # history (immune to both imported history and release pruning), verified by
    # blobless-cloning each repo. These override the crawled date.
    "Minimig":       "2017-06-15",  # repo had pre-MiSTer Minimig history back to 2011
    "Ti994a":        "2018-05-27",  # repo recycled from ColecoVision (early commits are CV)
    "C128":          "2022-05-20",  # forked from C64_MiSTer (carried C64's 2017 history)
    "Atari7800":     "2021-04-17",  # imported history dated 2019
    "MSX1":          "2022-01-05",  # forked from MSX
    "SuperVision":   "2022-06-11",  # imported history dated 2020
    "TRS-80":        "2020-05-22",  # repo also holds the older ht1080z core (2019)
    "PSX":           "2022-05-11",  # long WIP; first public build 2022-05 (commits from 2021)
    "PC88":          "2022-01-07",  # WIP commits from 2021
    "VC4000":        "2021-09-14",  # WIP commits from early 2021
    "ChannelF":      "2021-10-26",  # WIP commits from early 2021
    "CDi":           "2025-02-14",  # WIP commits from 2024
    "VT52":          "2024-11-14",  # WIP commits from Sep 2024
    "Altair8800":    "2018-11-13",  # WIP commits from Aug 2018
    "NeoGeo":        "2019-09-07",  # first release ~7 weeks after first commit
    "Jaguar":        "2026-05-26",  # years of WIP; actually launched May 2026
    "GameAndWatch":  "2026-05-10",  # new core; repo had imported dev history from 2023
    "Tamagotchi":    "2026-05-15",  # new core; repo had imported dev history from 2023
}


def core_name(title):
    """Core name = the .rbf stem with the `_YYYYMMDD` build-date suffix stripped."""
    return _CORE_DATE_RE.sub("", title or "").rstrip("_ ")


def core_repo_base(title):
    """Repo base name for a console/computer/other core title.

    The catalog title is the .rbf stem (e.g. `C64_20260603`); strip the
    `_YYYYMMDD` build-date suffix to get the core name, which maps to the
    per-core repo `MiSTer-devel/<core>_MiSTer`.
    """
    core = core_name(title)
    return CORE_REPO_OVERRIDES.get(core, core)


def apply_frozen_core_dates(con):
    """Set release_date from CORE_FROZEN_DATES for cores the crawl can't reach.

    These hand-verified debut dates win for their cores regardless of any
    build-date suffix, and never change on re-export (the values are pinned in
    code), so old cores can't drift to look newly released.
    """
    n = 0
    for row in con.execute(
        "SELECT source_id, path, title FROM catalog WHERE system IN ('console','computer','other')"
    ).fetchall():
        d = CORE_FROZEN_DATES.get(core_name(row["title"]))
        if d:
            con.execute(
                "UPDATE catalog SET release_date=? WHERE source_id=? AND path=?",
                (d, row["source_id"], row["path"]),
            )
            n += 1
    if n:
        log(f"  applied {n} frozen core debut dates")


def cmd_core_repos(args):
    con = connect()
    rows = con.execute(
        "SELECT DISTINCT title FROM catalog WHERE system IN ('console','computer','other')"
    ).fetchall()
    # de-dupe by repo base name (a core can appear under multiple sources)
    bases = {}
    for r in rows:
        base = core_repo_base(r["title"])
        if base:
            bases.setdefault(base, r["title"])
    bases = dict(sorted(bases.items()))
    if args.limit:
        bases = dict(list(bases.items())[: args.limit])
    log(f"crawling {len(bases)} console/computer/other core repos ...")
    org = list_org_repos()
    crawled = {
        r["repo"]: r["crawled_at"]
        for r in con.execute("SELECT repo, crawled_at FROM core_repos").fetchall()
    }
    hit = miss = skipped = 0
    for i, base in enumerate(bases, 1):
        # resolve the real repo name from the org listing (case-insensitive,
        # like GitHub's own repo lookup — some repos spell the suffix _MISTer)
        meta = org.get(f"{base}_MiSTer".lower())
        if meta is None:
            # not in the org: either it never existed (the old code burned a
            # 404 here every run) or it went private/archived-and-hidden —
            # keep any previously-crawled row, there's nothing new to fetch
            miss += 1
            continue
        # keep the constructed name as the storage key (what earlier crawls
        # wrote); GitHub's API accepts it case-insensitively either way
        full = f"{ARCADE_REPO_ORG}/{base}_MiSTer"
        prev = crawled.get(full)
        if prev and not getattr(args, "force", False) and iso_z(meta.get("pushed_at")) <= iso_z(prev):
            hit += 1
            skipped += 1
            continue
        try:
            first, last, count = repo_commit_bounds(full)
        except Exception as e:
            log(f"  [{i}/{len(bases)}] {full}: ERROR {e}")
            continue
        if not first:
            miss += 1
            continue
        hit += 1
        con.execute(
            "INSERT INTO core_repos(repo,core,html_url,first_commit,last_commit,commits,crawled_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(repo) DO UPDATE SET "
            "first_commit=excluded.first_commit, last_commit=excluded.last_commit, "
            "commits=excluded.commits, crawled_at=excluded.crawled_at",
            (full, base, f"https://github.com/{full}", first, last, count, now_iso()),
        )
        if i % 20 == 0 or i == len(bases):
            con.commit()
            log(f"  [{i}/{len(bases)}] {full}  debut={first[:10]}  updated={last[:10] if last else '?'}")
    con.commit()
    join_core_repos_to_catalog(con)
    apply_frozen_core_dates(con)
    con.commit()
    con.close()
    log(f"core repos crawl done. {hit} resolved, {miss} unresolved.")


def join_core_repos_to_catalog(con):
    """Attach per-core repo debut dates to console/computer/other catalog rows."""
    repos = con.execute("SELECT repo, core, first_commit, last_commit FROM core_repos").fetchall()
    by_base = {r["core"]: r for r in repos}
    n = 0
    for row in con.execute(
        "SELECT source_id, path, title FROM catalog WHERE system IN ('console','computer','other')"
    ).fetchall():
        r = by_base.get(core_repo_base(row["title"]))
        if r:
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (r["repo"], r["first_commit"], r["last_commit"], row["source_id"], row["path"]),
            )
            n += 1
    log(f"  joined {n} console/computer/other titles to a core repo (debut dates attached)")


# --- command: enrich-mra (year / manufacturer from MRA XML) ---------------

# Repos that ship the MRA XML for a given source (for year/manufacturer/rbf).
MRA_REPOS = [
    ("distribution_mister", "MiSTer-devel/Distribution_MiSTer", "main"),
    ("jtbindb", "jotego/jtcores_mister", "main"),
    # Coin-Op keeps db.json.zip on the `db` branch but the MRAs live on
    # `develop`; parsing them fills the rbf (Core column), setname, year and
    # manufacturer for the ~57 Coin-Op rows that used to have none — the
    # blank rbf was why their Core cell fell back to the repo-name label
    # "Distribution-MiSTerFPGA".
    ("coinop", "Coin-OpCollection/Distribution-MiSTerFPGA", "develop"),
]


def _sparse_arcade_clone(full_name, branch):
    """Blobless sparse clone of a repo's _Arcade folder; returns the local dir."""
    name = full_name.split("/")[-1]
    repodir = DATA / "repos" / name
    if not (repodir / ".git").exists():
        repodir.parent.mkdir(parents=True, exist_ok=True)
        log(f"cloning {full_name} (blobless, sparse _Arcade/*.mra) ...")
        subprocess.check_call([
            "git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
            "--single-branch", "-b", branch,
            f"https://github.com/{full_name}", str(repodir),
        ])
        # Non-cone pattern: only top-level MRAs. Skips nested dirs like
        # _Arcade/_alternatives/_M.I.A./ whose trailing-dot names are illegal on NTFS.
        subprocess.check_call(["git", "-C", str(repodir), "sparse-checkout", "set", "--no-cone", "/_Arcade/*.mra"])
        # protectNTFS=false lets checkout proceed past NTFS-illegal paths in
        # excluded subdirs (e.g. _alternatives/_M.I.A./); sparse skips writing them.
        subprocess.check_call(["git", "-C", str(repodir), "-c", "core.protectNTFS=false", "checkout"])
    else:
        # Refresh a cached clone. Distribution force-pushes (rewrites history),
        # so --ff-only aborts and would silently leave a stale checkout missing
        # newly-added MRAs. On failure, wipe and re-clone so enrichment always
        # sees the current MRAs. (On CI the dir never exists, so this is only for
        # a warm cache, e.g. local runs.)
        pull = subprocess.run(["git", "-C", str(repodir), "pull", "--ff-only"])
        if pull.returncode != 0:
            log(f"  {full_name}: ff-only pull failed (force-push?); re-cloning fresh")
            _rmtree_force(repodir)
            return _sparse_arcade_clone(full_name, branch)
    return repodir


def _rmtree_force(path):
    """rmtree that survives Windows' read-only .git pack files: on a permission
    error, clear the read-only bit and retry so the delete actually completes
    (a plain rmtree leaves a half-removed dir that breaks the next clone)."""
    def on_error(func, p, exc_info):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=on_error)


def cmd_enrich_mra(args):
    """Parse MRA XML from each source's repo to add year/manufacturer/rbf.

    Done per-source so identically-named MRAs in different sources (e.g. a
    MiSTer-devel '1942' vs a Jotego '1942') don't clobber each other's rbf.
    """
    import xml.etree.ElementTree as ET

    con = connect()
    grand = 0
    for source_id, full_name, branch in MRA_REPOS:
        repodir = _sparse_arcade_clone(full_name, branch)
        meta = {}
        for mra in (repodir / "_Arcade").glob("*.mra"):
            try:
                root = ET.parse(mra).getroot()
                def gx(tag):
                    el = root.find(tag)
                    return el.text.strip() if el is not None and el.text else None
                meta[mra.name] = {"year": gx("year"), "manufacturer": gx("manufacturer"),
                                  "rbf": gx("rbf"), "setname": gx("setname")}
            except Exception:
                continue
        n = 0
        for row in con.execute(
            "SELECT path FROM catalog WHERE system='arcade' AND source_id=?", (source_id,)
        ).fetchall():
            m = meta.get(Path(row["path"]).name)
            if m:
                con.execute(
                    "UPDATE catalog SET year=?, manufacturer=?, rbf=?, setname=? WHERE source_id=? AND path=?",
                    (m["year"], m["manufacturer"], m["rbf"], m["setname"], source_id, row["path"]),
                )
                n += 1
        log(f"  {source_id}: enriched {n} titles from {len(meta)} MRAs")
        grand += n
    con.commit()
    con.close()
    log(f"enrich-mra done: {grand} arcade titles enriched.")


# --- command: jtcores (Jotego release dates from monorepo folders) --------

JT_REPO = "jotego/jtcores"


def jt_public_cores():
    """Read jtbindb and return folder names (jt<name>.rbf -> <name>)."""
    raw = http_get(SOURCES[1]["db_url"])  # jtbindb
    z = zipfile.ZipFile(BytesIO(raw))
    d = json.loads(z.read(z.namelist()[0]))
    cores = {}
    for path in d.get("files", {}):
        name = Path(path).name.lower()
        if name.startswith("jt") and name.endswith(".rbf"):
            rbf = name[:-4]            # jtcps1
            folder = rbf[2:]          # cps1
            cores[folder] = rbf
    return cores


def cmd_jtcores(args):
    con = connect()
    cores = jt_public_cores()
    log(f"jtcores: {len(cores)} public cores to date from {JT_REPO}/cores/*")
    items = sorted(cores.items())
    if args.limit:
        items = items[: args.limit]
    # incremental: one pushed_at check on the monorepo gates the whole folder
    # crawl — no push since the last crawl means no folder's bounds moved. A
    # core newly graduated to public (jtbindb change, not a jtcores push) can
    # still appear without a push, so never-crawled folders are always fetched.
    last_crawl = con.execute("SELECT MAX(crawled_at) FROM jt_cores").fetchone()[0]
    if last_crawl and not getattr(args, "force", False):
        meta = gh_api(f"/repos/{JT_REPO}")
        if iso_z(meta.get("pushed_at")) <= iso_z(last_crawl):
            known = {r["folder"] for r in con.execute("SELECT folder FROM jt_cores").fetchall()}
            skipped = sum(1 for f, _ in items if f in known)
            items = [(f, r) for f, r in items if f not in known]
            log(f"  {JT_REPO} unchanged since last crawl — skipping {skipped} known folders")
    for i, (folder, rbf) in enumerate(items, 1):
        try:
            first, last, count = repo_commit_bounds(JT_REPO, path=f"cores/{folder}")
        except Exception as e:
            log(f"  [{i}/{len(items)}] {folder}: ERROR {e}")
            continue
        if count == 0:
            continue
        con.execute(
            "INSERT INTO jt_cores(folder,rbf,first_commit,last_commit,commits,crawled_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(folder) DO UPDATE SET "
            "first_commit=excluded.first_commit, last_commit=excluded.last_commit, "
            "commits=excluded.commits, crawled_at=excluded.crawled_at",
            (folder, rbf, first, last, count, now_iso()),
        )
        if i % 20 == 0 or i == len(items):
            con.commit()
            log(f"  [{i}/{len(items)}] {rbf}  debut={first[:10] if first else '?'}  updated={last[:10] if last else '?'}")
    con.commit()
    join_jt_to_catalog(con)
    apply_jt_frozen_dates(con)
    con.commit()
    con.close()
    log("jtcores crawl done.")


def join_jt_to_catalog(con):
    """Attach Jotego dates to arcade catalog rows whose rbf is jt<folder>.

    Undated rows get repo + debut + last_update. Rows already dated BY A
    PREVIOUS JT JOIN (repo points at the monorepo) get only last_update
    refreshed — debuts stay frozen while the "latest update" signal tracks the
    daily crawl. Rows dated by another source keep that source's dates."""
    jt = {r["folder"]: r for r in con.execute("SELECT * FROM jt_cores").fetchall()}
    n = m = 0
    for row in con.execute(
        "SELECT source_id, path, rbf, release_date, repo FROM catalog "
        "WHERE system='arcade' AND rbf IS NOT NULL"
    ).fetchall():
        rbf = row["rbf"].lower()
        folder = rbf[2:] if rbf.startswith("jt") else rbf
        r = jt.get(folder)
        if not r:
            continue
        if row["release_date"] is None:
            debut = JT_CORE_FROZEN_DATES.get(folder, r["first_commit"])
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (JT_REPO + f" (cores/{folder})", debut, r["last_commit"],
                 row["source_id"], row["path"]),
            )
            n += 1
        elif (row["repo"] or "").startswith(JT_REPO):
            con.execute(
                "UPDATE catalog SET last_update=? WHERE source_id=? AND path=?",
                (r["last_commit"], row["source_id"], row["path"]),
            )
            m += 1
    log(f"  joined {n} Jotego arcade titles to release dates; refreshed last_update on {m}")


# The jtcores monorepo dates a core by the first commit that touched its
# cores/<folder>/ path — but Jotego MERGED dozens of long-standing standalone
# cores into that folder layout in a big Feb-2023 reorg (and the GitHub commits
# API doesn't follow the rename), so every pre-existing core inherited a bogus
# 2023-02-04/05/12/15 "debut". The monorepo did NOT preserve those cores' own
# history on merge, so the real dates come from the surviving archived standalone
# repos (created_at) or Jotego's documented public-release announcements. The
# folder date is wrong in BOTH directions: too-new for old cores merged in, and
# too-OLD for cps3 (its dev folder predates the actual 2026 release by 3 years).
# Each entry below is frozen to the core's real first MiSTer appearance; basis +
# confidence noted per line. Folders deliberately left at their ~Feb-2023 monorepo
# date because that IS ~their real debut: s18, outrun, shanon (Sega, ~2023 dev),
# karnov/contra/castle (public early Feb 2023), bubl (Taito, ~2023).
JT_CORE_FROZEN_DATES = {
    # Capcom CPS
    "cps1":  "2020-01-12",  # jtcps repo created_at (CPS1 origin); HIGH
    "cps15": "2020-01-12",  # CPS1.5 = same CPS1 hardware/core; HIGH
    "cps2":  "2021-01-29",  # CPS2 public beta ("CPS2 is here!", RetroRGB); HIGH
    "cps3":  "2026-06-10",  # JTCPS3 first release (SF III / Red Earth), Jun 2026; HIGH
    # Sega System 16
    "s16":   "2022-01-17",  # jts16 repo created_at (public Mar 2022); HIGH
    "s16b":  "2022-01-17",  # System 16B = same jts16 core; HIGH
    # Konami pre-/System-1 wave — jtkicker repo (2021-11-13) = dev origin of the
    # wave; individual games went public across 2022. Anchored to the earliest
    # (anti-inflation). MEDIUM for the non-kicker members.
    "kicker": "2021-11-13", "track": "2021-11-13", "mikie": "2021-11-13",
    "roc":    "2021-11-13", "sbaskt": "2021-11-13", "pinpon": "2021-11-13",
    "yiear":  "2021-11-13", "labrun": "2021-11-13", "roadf":  "2021-11-13",
    "comsc":  "2021-11-13", "flane":  "2021-11-13", "mx5k":   "2021-11-13",
    # Data East DEC0 — public April 2022 batch (Robocop/Bad Dudes/Heavy Barrel/
    # Midnight Resistance/Sly Spy/Hippodrome). HIGH (batch), MEDIUM per-title.
    "cop":    "2022-04-08", "ninja": "2022-04-08",
    "midres": "2022-04-08", "slyspy": "2022-04-08",
    # Technos — public Dec 2 2022 batch. HIGH for dd/dd2/kunio, MEDIUM kchamp.
    "dd":   "2022-12-02", "dd2": "2022-12-02",
    "kunio": "2022-12-02", "kchamp": "2022-12-02",
    # Singles
    "rastan": "2022-04-01",  # Taito Rastan, beta Apr 2022; MEDIUM
    "vigil":  "2022-07-01",  # Irem Vigilante, public Jul 2022; HIGH
    "pang":   "2022-08-05",  # Mitchell Pang!, public Aug 5 2022; HIGH
    "kiwi":   "2022-11-12",  # Taito New Zealand Story, beta Nov 12 2022; HIGH
}


def apply_jt_frozen_dates(con):
    """Override the bogus Feb-2023 jtcores-monorepo-migration dates with each
    Jotego core's real debut from JT_CORE_FROZEN_DATES. Unlike the other frozen
    helpers this REPLACES the existing value (the migration date is wrong, not
    merely missing), keyed by the monorepo folder (rbf = jt<folder>)."""
    n = 0
    for folder, debut in JT_CORE_FROZEN_DATES.items():
        cur = con.execute(
            "UPDATE catalog SET release_date=? WHERE system='arcade' AND lower(rbf)=?",
            (debut, "jt" + folder),
        )
        n += cur.rowcount
    if n:
        log(f"  corrected {n} Jotego arcade titles off the Feb-2023 migration date")


# --- command: coinop (Coin-Op release dates from commit messages) ---------

COINOP_REPO = "Coin-OpCollection/Distribution-MiSTerFPGA"
# Coin-Op commit subjects look like "<Title> Release|Update|Beta|Alpha YYYYMMDD".
# Beta/Alpha are often a game's first public appearance, so they count as debuts;
# we keep the EARLIEST date per title. Some commits bundle several games
# ("Hachoo!, E.D.F, In Your Face Beta ...") so the title part is split.
COINOP_RE = re.compile(r"^(.+?)\s+(?:Release|Update|Beta|Alpha)\s+(\d{8})", re.IGNORECASE)
COINOP_SPLIT = re.compile(r"\s*(?:,|/|&|\band\b)\s*", re.IGNORECASE)


def cmd_coinop(args):
    con = connect()
    log(f"coinop: scanning {COINOP_REPO}@develop commit messages ...")
    page = 1
    found = {}
    while True:
        data, hdrs = gh_api(
            f"/repos/{COINOP_REPO}/commits?sha=develop&per_page=100&page={page}", want_headers=True
        )
        if not data:
            break
        for c in data:
            msg = c["commit"]["message"].splitlines()[0]
            m = COINOP_RE.match(msg)
            if m:
                ymd = m.group(2)
                rel_date = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
                cdate = c["commit"]["committer"]["date"]
                for raw in COINOP_SPLIT.split(m.group(1).strip()):
                    title = raw.strip(" !")
                    key = norm_key(title)
                    if len(key) < 4:
                        continue
                    # keep the EARLIEST date per title (a game's MiSTer debut)
                    if key not in found or rel_date < found[key][0]:
                        found[key] = (rel_date, cdate, title)
        if 'rel="next"' not in hdrs.get("Link", ""):
            break
        page += 1
    for key, (rel_date, cdate, title) in found.items():
        con.execute(
            "INSERT INTO coinop_releases(title,release_date,commit_date) VALUES(?,?,?) "
            "ON CONFLICT(title) DO UPDATE SET release_date=excluded.release_date, commit_date=excluded.commit_date",
            (title, rel_date, cdate),
        )
    log(f"  parsed {len(found)} dated Coin-Op releases")
    join_coinop_to_catalog(con)
    con.commit()
    con.close()
    log("coinop backfill done.")


# Debut dates for Coin-Op games that the commit-message parser can't reach
# (added in dateless bulk commits or under a system name). Derived objectively
# from each MRA's first-add commit in the Coin-Op repo git history (blobless
# clone + `git log --diff-filter=A`), which is the game's debut in the
# distribution; the ~2022-09-22 cluster is the repo's initial import seed (the
# armedf/terracresta cores were already built by then, so those games were
# genuinely playable). Frozen here so they never drift. Keyed by game name.
COINOP_FROZEN_DATES = {
    'Armed F': '2022-09-22',
    'Armed Police Batrider': '2025-03-31',
    'Battle Bakraid - Unlimited Version': '2025-03-31',
    'Battle Garegga': '2023-09-10',
    'Chouji Meikyuu Legion': '2022-09-22',
    'Crazy Climber 2': '2022-09-22',
    "Demon's World - Horror Story": '2023-06-10',
    'Gang Wars': '2022-11-16',
    'Hellfire': '2023-05-22',
    'Hishou Zame': '2025-12-14',
    'Iga Ninjyutsuden': '2023-09-23',
    'Ikari III - The Rescue': '2022-10-19',
    'Kid no Hore Hore Daisakusen': '2022-09-22',
    'Kozure Ookami': '2022-09-22',
    'Kyukyoku Tiger': '2025-12-14',
    'Mahou Daisakusen': '2025-03-31',
    'Out Zone': '2022-09-22',
    'P.O.W. - Prisoners of War': '2022-09-28',
    'Paddle Mania': '2023-03-30',
    'Pipi & Bibis - Whoopee!!': '2022-12-25',
    'Prehistoric Isle in 1930': '2022-09-25',
    'Rally Bike - Dash Yarou': '2023-06-02',
    'Rod-Land': '2023-05-13',
    'SAR - Search And Rescue': '2022-09-28',
    'Same! Same! Same!': '2023-05-26',
    'Sei Senshi Amatelass': '2022-09-22',
    'Shippu Mahou Daisakusen': '2025-03-31',
    'Sky Adventure': '2022-11-16',
    'Sky Soldiers': '2022-12-23',
    'Soldam': '2023-05-19',
    'Street Smart': '2022-09-28',
    'Tatakae! Big Fighter': '2022-09-22',
    'Teenage Mutant Ninja Turtles - Turtles in Time': '2025-04-17',
    'Terra Cresta': '2022-09-22',
    'Terra Force': '2022-09-22',
    'The Lord of King': '2023-07-01',
    'The Next Space': '2023-03-30',
    'Time Soldiers': '2022-12-23',
    'Truxton - Tatsujin': '2022-09-22',
    'Truxton II - Tatsujin Oh': '2022-09-22',
    'Vimana': '2023-05-26',
    'Zero Wing': '2023-05-22',
}
_COINOP_FROZEN_NORM = {norm_key(k): v for k, v in COINOP_FROZEN_DATES.items()}


def join_coinop_to_catalog(con):
    """Attach Coin-Op release dates to coinop catalog titles by normalized prefix."""
    rels = con.execute("SELECT title, release_date, commit_date FROM coinop_releases").fetchall()
    # index by normalized key; release titles are the short/canonical form.
    # Sort keys longest-first so the most specific release name wins (e.g.
    # "snowbros2" is preferred over "snowbros" for "Snow Bros. 2 ...").
    by_key = {norm_key(r["title"]): r for r in rels}
    keys = sorted(by_key, key=len, reverse=True)
    n = 0
    for row in con.execute(
        "SELECT source_id, path, title FROM catalog WHERE source_id='coinop'"
    ).fetchall():
        ck = norm_key(row["title"])
        match = None
        for rk in keys:
            # catalog title carries region/version suffixes the release name lacks,
            # so match if either is a prefix of the other (min length guards noise).
            if ck == rk or ck.startswith(rk) or (rk.startswith(ck) and len(ck) >= 5):
                match = by_key[rk]
                break
        if match:
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (COINOP_REPO, match["release_date"], match["commit_date"],
                 row["source_id"], row["path"]),
            )
            n += 1
        elif _COINOP_FROZEN_NORM.get(ck):
            con.execute(
                "UPDATE catalog SET repo=?, release_date=? WHERE source_id=? AND path=?",
                (COINOP_REPO, _COINOP_FROZEN_NORM[ck], row["source_id"], row["path"]),
            )
            n += 1
    log(f"  joined {n} Coin-Op titles to release dates")


# --- command: genre (arcade genre from MAME catver.ini, joined on setname) -

# Stable raw-accessible mirror of MAME's catver.ini (this copy tracks MAME 0.239).
# A newer catver would lift coverage slightly; 0.239 already matches ~88% of our
# setnames. Fetched at build time and cached locally (see CACHEDIR).
CATVER_URL = "https://raw.githubusercontent.com/libretro/mame2003-plus-libretro/master/metadata/catver.ini"


def fetch_catver():
    """Return the catver.ini text, caching the download under data/cache/."""
    CACHEDIR.mkdir(parents=True, exist_ok=True)
    cache = CACHEDIR / "catver.ini"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")
    log(f"  fetching catver.ini ...")
    text = http_get(CATVER_URL).decode("utf-8", errors="ignore")
    cache.write_text(text, encoding="utf-8")
    return text


def parse_catver(text):
    """Parse the [Category] section into {setname_lower: top_level_genre}.

    catver values look like 'Shooter / Flying Vertical' or 'Platform - Climb';
    collapse to the leading token so e.g. all shooters land under 'Shooter'.
    """
    cats = {}
    section = None
    for line in text.splitlines():
        if line.startswith("["):
            section = line.strip("[]")
            continue
        if section == "Category" and "=" in line:
            k, v = line.split("=", 1)
            v = re.split(r"[/-]", v)[0].strip()
            if v:
                cats[k.strip().lower()] = v
    return cats


# The MAME arcade DAT (cached by the image pipeline) carries year, manufacturer
# and cloneof per setname for every arcade machine — a far richer, newer source
# than catver. We mine it to (a) fill arcade rows whose MRA shipped no year /
# manufacturer and (b) supply the parent setname so clone rows can inherit a
# parent's genre/year/manufacturer. Loaded lazily, guarded: on a fresh checkout
# the DAT may not be cached yet, in which case these fills simply no-op.
MAME_DAT = CACHEDIR / "MAME_arcade.dat"
# The DAT is 71 MB and gitignored, so it's absent on CI. We derive a slim
# {setname: year/manufacturer/parent/desc} map from it and commit that (0.5 MB
# gzipped) so the daily build has the same data. Regenerated locally via
# `mame-meta` whenever a new DAT is dropped (the raw DAT is a manual local pass).
MAME_META_GZ = CACHEDIR / "mame_meta.json.gz"
_DAT_MACHINE = re.compile(r'<machine\s+name="([^"]+)"([^>]*)>(.*?)</machine>', re.S)


def parse_dat_meta(txt):
    """{setname_lower: {'year','manufacturer','parent','desc'}} from DAT XML text."""
    import html
    meta = {}
    for m in _DAT_MACHINE.finditer(txt):
        name, attrs, body = m.group(1).lower(), m.group(2), m.group(3)
        co = re.search(r'cloneof="([^"]+)"', attrs)
        yr = re.search(r"<year>([^<]*)</year>", body)
        mf = re.search(r"<manufacturer>([^<]*)</manufacturer>", body)
        de = re.search(r"<description>([^<]*)</description>", body)
        meta[name] = {
            "year": (yr.group(1).strip() if yr and yr.group(1).strip() not in ("", "????") else ""),
            "manufacturer": (html.unescape(mf.group(1)).strip() if mf else ""),
            "parent": (co.group(1).lower() if co else None),
            "desc": (html.unescape(de.group(1)).strip() if de else ""),
        }
    return meta


def load_arcade_dat_meta():
    """{setname_lower: {'year','manufacturer','parent','desc'}} for arcade fills.

    Prefers the raw DAT when cached locally (always current); else falls back to
    the committed derived artifact so CI has the same data. {} if neither exists."""
    if MAME_DAT.exists():
        return parse_dat_meta(MAME_DAT.read_text(encoding="utf-8", errors="ignore"))
    if MAME_META_GZ.exists():
        import gzip
        return json.loads(gzip.decompress(MAME_META_GZ.read_bytes()).decode("utf-8"))
    return {}


def _norm_arcade_title(s):
    """Normalize a title/description for setname reverse-matching: drop any
    parentheticals (region/rev/board qualifiers) and keep only alphanumerics."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", s or "").lower())


def build_dat_desc_index(dat):
    """{normalized_description: setname} for recovering a setname from a title
    when no join key exists (e.g. coinop/libretro rows). Prefers the parent set
    when several region/rev variants share a normalized description — they all
    carry the same year/manufacturer, so the choice only affects the join key."""
    index = {}
    for sn, e in (dat or {}).items():
        key = _norm_arcade_title(e.get("desc", ""))
        if not key:
            continue
        if key not in index or e.get("parent") is None:
            index[key] = sn
    return index


def cmd_mame_meta(args):
    """Derive the committed mame_meta.json.gz from the local raw MAME DAT."""
    import gzip
    if not MAME_DAT.exists():
        log(f"mame-meta: {MAME_DAT} not found — nothing to derive (raw DAT is a local pass).")
        return
    meta = parse_dat_meta(MAME_DAT.read_text(encoding="utf-8", errors="ignore"))
    blob = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    MAME_META_GZ.write_bytes(gzip.compress(blob, mtime=0))
    log(f"mame-meta: wrote {MAME_META_GZ} ({len(meta)} machines, {MAME_META_GZ.stat().st_size/1048576:.1f} MB gz)")


def load_manifest_setnames():
    """{display_title: setname} from the image manifest. Many backfilled arcade
    rows have a setname only here (resolved by the image pipeline), not in
    catalog.setname, so this recovers genre/manufacturer/year for them. {} if absent."""
    mf = CACHEDIR / "image_manifest.json"
    if not mf.exists():
        return {}
    data = json.loads(mf.read_text(encoding="utf-8"))
    return {e["title"]: e["setname"] for e in data if e.get("setname")}


def local_catver():
    """catver genre map from the local cache only (no network); {} if absent."""
    cache = CACHEDIR / "catver.ini"
    if not cache.exists():
        return {}
    return parse_catver(cache.read_text(encoding="utf-8", errors="ignore"))


def genre_for(setname, cats, dat):
    """catver genre for a setname, falling back to its DAT parent's genre."""
    if not setname:
        return ""
    sl = setname.lower()
    g = cats.get(sl)
    if g:
        return g
    parent = (dat.get(sl) or {}).get("parent")
    return cats.get(parent, "") if parent else ""


def cmd_genre(args):
    con = connect()
    cats = parse_catver(fetch_catver())
    dat = load_arcade_dat_meta()
    log(f"genre: {len(cats)} setname->genre entries from catver.ini"
        + (f"; {len(dat)} DAT machines for parent fallback" if dat else ""))
    rows = con.execute(
        "SELECT source_id, path, setname FROM catalog WHERE system='arcade' AND setname IS NOT NULL"
    ).fetchall()
    n = 0
    for row in rows:
        g = genre_for(row["setname"], cats, dat)
        if g:
            con.execute(
                "UPDATE catalog SET genre=? WHERE source_id=? AND path=?",
                (g, row["source_id"], row["path"]),
            )
            n += 1
    con.commit()
    con.close()
    log(f"  joined {n}/{len(rows)} arcade titles (with a setname) to a genre")


# --- command: mad (arcade metadata from the MiSTer Arcade Database) --------

# Toryalai1's MiSTer Arcade Database, joined on MAME setname: rotation, flip,
# resolution, players, controls. The source CSV on main, NOT the compiled
# mad_db.json.zip — the compiled db drops rotation from nearly every entry
# (8 of ~1965 carry it), while the CSV has it for all rows.
MAD_URL = ("https://raw.githubusercontent.com/Toryalai1/MiSTer_ArcadeDatabase"
           "/main/ArcadeDatabase.csv")

_MAD_ROTATION = {
    "horizontal": "Horizontal", "horizontal (180)": "Horizontal (180)",
    "vertical (cw)": "Vertical (CW)", "vertical (ccw)": "Vertical (CCW)",
}


def fetch_mad(refresh=False):
    """Return the MAD CSV text, caching the download under data/cache/."""
    CACHEDIR.mkdir(parents=True, exist_ok=True)
    cache = CACHEDIR / "ArcadeDatabase.csv"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8", errors="ignore")
    log(f"  fetching ArcadeDatabase.csv (MAD) ...")
    text = http_get(MAD_URL).decode("utf-8", errors="ignore")
    cache.write_text(text, encoding="utf-8")
    return text


def parse_mad(text):
    """{setname_lower: {rot,res,plr,ctl,spc,flip}} — display-ready values.

    The CSV vocabulary is uneven ('n-a'/'' blanks, '15 kHz' vs '15kHz',
    'trackball' vs 'Trackball'), so values are normalized here once; the
    export and site use them verbatim. Absent fields are omitted entirely.
    """
    import csv, io
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        sn = (r.get("setname") or "").strip().lower()
        if not sn or sn in out:  # a few dupe setnames — first row wins
            continue
        def val(k):
            v = (r.get(k) or "").strip()
            return "" if v.lower() == "n-a" else v
        e = {}
        rot = val("rotation").lower()
        if rot:
            e["rot"] = _MAD_ROTATION.get(rot, rot.title())
        res = val("resolution").replace(" ", "")
        if res:
            e["res"] = res
        if val("players"):
            e["plr"] = val("players")
        # combined controls: move inputs + button count ('8-way · 3 buttons');
        # 0 buttons just means no fire button — showing the stick alone reads best
        move, btn = val("move_inputs"), val("num_buttons")
        ctl = [move] if move else []
        if btn and btn != "0":
            ctl.append(btn + (" button" if btn == "1" else " buttons"))
        if ctl:
            e["ctl"] = " · ".join(ctl)
        spc = val("special_controls")
        if spc:
            e["spc"] = spc[0].upper() + spc[1:]
        # blank flip = unverified (leave the cell empty); an explicit 'no'
        # is a verified result and worth showing distinctly from unknown
        flip = val("flip").lower()
        if flip == "yes":
            e["flip"] = "Yes"
        elif flip == "no":
            e["flip"] = "No"
        if e:
            out[sn] = e
    return out


def local_mad():
    """MAD metadata map from the local cache only (no network); {} if absent."""
    cache = CACHEDIR / "ArcadeDatabase.csv"
    if not cache.exists():
        return {}
    return parse_mad(cache.read_text(encoding="utf-8", errors="ignore"))


def mad_for(setname, mad, dat):
    """MAD entry for a setname, falling back to its DAT parent's entry."""
    if not setname:
        return {}
    sl = setname.lower()
    e = mad.get(sl)
    if e:
        return e
    parent = (dat.get(sl) or {}).get("parent")
    return mad.get(parent, {}) if parent else {}


def cmd_mad(args):
    mad = parse_mad(fetch_mad(refresh=True))
    log(f"mad: {len(mad)} setname->metadata entries from ArcadeDatabase.csv")


# --- command: specs (provisional arcade specs for rows not yet in MAD) -----

# libretro's mame2003-plus listxml (same host as catver) carries orientation,
# players, control type and button count per game — enough to fill blank
# Rotation/Players/Controls/Special cells for brand-new arcade titles MAD hasn't
# catalogued yet. Values are shown grayed (provisional) and MAD overwrites them
# the moment it catches up. Only ~22 MB, so we derive a slim gz and commit that
# (like mame_meta.json.gz); resolution (a CRT scan class) and flip aren't
# derivable here and stay MAD-only.
SPECS_URL = ("https://raw.githubusercontent.com/libretro/mame2003-plus-libretro"
             "/master/metadata/mame2003-plus.xml")
SPECS_GZ = CACHEDIR / "mame2003_specs.json.gz"
_SPECS_GAME = re.compile(r'<game\s+name="([^"]+)"[^>]*>(.*?)</game>', re.S)
# movement controls -> the "move" half of the Controls cell (parse_mad's format)
_SPECS_MOVE = {
    "joy2way": "2-way", "joy4way": "4-way", "joy8way": "8-way",
    "doublejoy2way": "Double 2-way", "doublejoy4way": "Double 4-way",
    "doublejoy8way": "Double 8-way", "vjoy2way": "2-way", "stick": "Analog",
}
# non-joystick controls -> Special Controls cell
_SPECS_SPECIAL = {
    "dial": "Dial", "paddle": "Paddle", "trackball": "Trackball",
    "lightgun": "Lightgun", "pedal": "Pedal",
}


def parse_specs(text):
    """{setname_lower: {rot,plr,ctl,spc}} from mame2003-plus.xml, display-ready
    in the same vocabulary parse_mad emits so provisional cells read identically."""
    out = {}
    for g in _SPECS_GAME.finditer(text):
        name, body = g.group(1).lower(), g.group(2)
        if name in out:
            continue
        e = {}
        o = re.search(r'orientation="([^"]+)"', body)
        if o:
            ori = o.group(1).lower()
            if ori == "vertical":
                e["rot"] = "Vertical"
            elif ori == "horizontal":
                e["rot"] = "Horizontal"
        inp = re.search(r"<input([^>]*)>", body)
        if inp:
            ia = inp.group(1)
            pl = re.search(r'players="(\d+)"', ia)
            if pl and pl.group(1) != "0":
                e["plr"] = pl.group(1)
            ct = re.search(r'control="([^"]+)"', ia)
            control = ct.group(1).lower() if ct else ""
            move = _SPECS_MOVE.get(control, "")
            if control in _SPECS_SPECIAL:
                e["spc"] = _SPECS_SPECIAL[control]
            bt = re.search(r'buttons="(\d+)"', ia)
            ctl = [move] if move else []
            if bt and bt.group(1) != "0":
                n = bt.group(1)
                ctl.append(n + (" button" if n == "1" else " buttons"))
            if ctl:
                e["ctl"] = " · ".join(ctl)
        if e:
            out[name] = e
    return out


def local_specs():
    """Provisional-specs map from the committed gz only (no network); {} if absent."""
    if not SPECS_GZ.exists():
        return {}
    import gzip
    return json.loads(gzip.decompress(SPECS_GZ.read_bytes()).decode("utf-8"))


def specs_for(setname, specs, dat):
    """Provisional-specs entry for a setname, falling back to its DAT parent's."""
    if not setname:
        return {}
    sl = setname.lower()
    e = specs.get(sl)
    if e:
        return e
    parent = (dat.get(sl) or {}).get("parent")
    return specs.get(parent, {}) if parent else {}


def cmd_specs(args):
    import gzip
    specs = parse_specs(http_get(SPECS_URL).decode("utf-8", errors="ignore"))
    blob = json.dumps(specs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    SPECS_GZ.write_bytes(gzip.compress(blob, mtime=0))
    log(f"specs: {len(specs)} setname->specs from mame2003-plus.xml "
        f"-> {SPECS_GZ} ({SPECS_GZ.stat().st_size/1024:.0f} KB gz)")


# --- command: export ------------------------------------------------------

def cmd_export(args):
    con = connect()
    EXPORTDIR.mkdir(parents=True, exist_ok=True)

    # full catalog (deduped by normalized title, preferring rows with a release date)
    rows = [dict(r) for r in con.execute("SELECT * FROM catalog").fetchall()]
    (EXPORTDIR / "catalog.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    arcade = [r for r in rows if r["system"] == "arcade"]
    # dedupe arcade across sources by normalized title
    best = {}
    for r in arcade:
        k = norm_key(r["title"])
        cur = best.get(k)
        score = (1 if r.get("release_date") else 0, 1 if r.get("year") else 0)
        if cur is None or score > cur[0]:
            best[k] = (score, r)
    arcade_unique = sorted((v[1] for v in best.values()),
                           key=lambda r: (r.get("release_date") or "9999", r["title"]))
    (EXPORTDIR / "arcade.json").write_text(json.dumps(arcade_unique, indent=2), encoding="utf-8")

    # timeline of dated events, newest first
    events = [dict(r) for r in con.execute(
        "SELECT * FROM events ORDER BY ts DESC, source_id").fetchall()]
    with (EXPORTDIR / "timeline.jsonl").open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    # arcade release history derived from repos, newest debut first
    repo_rows = [dict(r) for r in con.execute(
        "SELECT * FROM arcade_repos ORDER BY first_commit DESC").fetchall()]
    (EXPORTDIR / "arcade_release_history.json").write_text(
        json.dumps(repo_rows, indent=2), encoding="utf-8")

    con.close()
    log(f"exports written to {EXPORTDIR}")
    log(f"  catalog.json: {len(rows)} rows")
    log(f"  arcade.json: {len(arcade_unique)} unique arcade titles")
    log(f"  arcade_release_history.json: {len(repo_rows)} cores with real dates")
    log(f"  timeline.jsonl: {len(events)} dated events")


# --- command: export-web (static site for GitHub Pages) -------------------

# Arcade rows that are BIOS/placeholders, not games — excluded from the site.
# Keyed by MAME setname. The IGS "PGM" entry is just the PGM motherboard BIOS.
# `ngp` is the NeoGeo Pocket system BIOS: Jotego ships its NGP core both as
# _Console/NeoGeoPocket.rbf and a redundant _Arcade/NeoGeo Pocket.mra (same repo,
# a handheld console, not an arcade game — its only "screenshot" is a blank boot
# screen). Drop the arcade duplicate; the console .rbf row is the canonical one.
ARCADE_EXCLUDE_SETNAMES = {"pgm", "ngp"}

_CORE_DATE_RE = re.compile(r"_(20\d{6})\b")

# Pretty base label per catalog `system` value.
_BASE_LABEL = {"arcade": "Arcade", "console": "Console", "computer": "Computer", "other": "Other"}

# Hardware maker per console core (keyed by core_name). Console cores have no MRA
# XML, so manufacturer isn't auto-derived; these are the original console makers.
CONSOLE_MANUFACTURER = {
    "NES": "Nintendo", "SNES": "Nintendo", "N64": "Nintendo", "Gameboy": "Nintendo",
    "Gameboy2P": "Nintendo", "GBA": "Nintendo", "GBA2P": "Nintendo", "SGB": "Nintendo",
    "PokemonMini": "Nintendo", "GameAndWatch": "Nintendo", "GnW": "Nintendo",
    "SMS": "Sega", "GameGear2P": "Sega", "MegaDrive": "Sega", "MegaCD": "Sega",
    "S32X": "Sega", "Saturn": "Sega",
    "Atari5200": "Atari", "Atari7800": "Atari", "AtariLynx": "Atari", "Jaguar": "Atari",
    "NeoGeo": "SNK", "NeoGeoPocket": "SNK",
    "TurboGrafx16": "NEC",
    "PSX": "Sony",
    "CDi": "Philips",
    "Intellivision": "Mattel",
    "ColecoVision": "Coleco",
    "Odyssey2": "Magnavox",
    "ChannelF": "Fairchild",
    "Astrocade": "Bally",
    "Arcadia": "Emerson",
    "Vectrex": "GCE",
    "WonderSwan": "Bandai", "Super_Vision_8000": "Bandai",
    "SuperVision": "Watara",
    "SCV": "Epoch",
    "CreatiVision": "VTech",
    "Casio_PV-1000": "Casio",
    "VC4000": "Interton",
    "AdventureVision": "Entex",
    "Gamate": "Bit Corporation",
    "AY-3-8500": "General Instrument",
    "MyVision": "Nichibutsu",
    "BBCBridgeCompanion": "BBC Enterprises",
}

# Hardware maker per computer core (keyed by core_name); same rationale as above.
# DIY/kit machines and obscure Eastern-bloc makers were web-verified.
COMPUTER_MANUFACTURER = {
    "C64": "Commodore", "C128": "Commodore", "C16": "Commodore", "VIC20": "Commodore",
    "PET2001": "Commodore", "Minimig": "Commodore",
    "Apple-I": "Apple", "Apple-II": "Apple", "MacPlus": "Apple",
    "ZX-Spectrum": "Sinclair", "ZX81": "Sinclair", "QL": "Sinclair",
    "ZXNext": "SpecNext", "SAMCoupe": "MGT", "TSConf": "TS-Labs",
    "AcornAtom": "Acorn", "AcornElectron": "Acorn", "BBCMicro": "Acorn", "Archie": "Acorn",
    "Amstrad": "Amstrad", "Amstrad-PCW": "Amstrad",
    "Atari800": "Atari", "AtariST": "Atari",
    "CoCo2": "Tandy", "CoCo3": "Tandy", "TRS-80": "Tandy", "Tandy1000": "Tandy",
    "AliceMC10": "Tandy / Matra",
    "PCXT": "IBM", "PCjr": "IBM",
    "PDP1": "DEC", "VT52": "DEC",
    "SharpMZ": "Sharp", "X68000": "Sharp",
    "PC88": "NEC",
    "Ti994a": "Texas Instruments",
    "ColecoAdam": "Coleco", "Aquarius": "Mattel", "TomyTutor": "Tomy",
    "Casio_PV-2000": "Casio", "SordM5": "Sord", "Svi328": "Spectravideo",
    "Laser310": "VTech", "eg2000": "EACA", "RX78": "Bandai",
    "TatungEinstein": "Tatung", "Lynx48": "Camputers", "Oric": "Oric",
    "Jupiter": "Jupiter Cantab", "Enterprise": "Enterprise Computers",
    "Interact": "Interact Electronics", "Altair8800": "MITS",
    "UK101": "Compukit", "EDSAC": "University of Cambridge",
    "MSX": "ASCII/Microsoft", "MSX1": "ASCII/Microsoft",
    "TK2000": "Microdigital",
    "MultiComp": "DIY (Grant Searle)",
    "Galaksija": "DIY (Yugoslavia)", "Homelab": "DIY (Hungary)", "Specialist": "DIY (Soviet)",
    "Ondra_SPO186": "Tesla", "PMD85": "Tesla", "IQ151": "ZPA",
    "BK0011M": "Elektronika", "Vector-06C": "Schetmash", "Apogee": "Soviet",
    "ORAO": "PEL Varaždin",
}

# Original-hardware release year per core (keyed by core_name). The year the real
# machine/console first shipped (not the MiSTer core). Obscure/Eastern-bloc years
# web-verified; a few modern DIY/clone cores and generic PC clones are left blank.
CORE_YEAR = {
    # consoles
    "NES": "1983", "SNES": "1990", "N64": "1996", "Gameboy": "1989", "Gameboy2P": "1989",
    "GBA": "2001", "GBA2P": "2001", "SGB": "1994", "PokemonMini": "2001",
    "GameAndWatch": "1980", "GnW": "1980",
    "SMS": "1985", "GameGear2P": "1990", "MegaDrive": "1988", "MegaCD": "1991",
    "S32X": "1994", "Saturn": "1994",
    "Atari5200": "1982", "Atari7800": "1986", "AtariLynx": "1989", "Jaguar": "1993",
    "NeoGeo": "1990", "NeoGeoPocket": "1998", "TurboGrafx16": "1987", "PSX": "1994",
    "CDi": "1991", "Intellivision": "1979", "ColecoVision": "1982", "Odyssey2": "1978",
    "ChannelF": "1976", "Astrocade": "1978", "Arcadia": "1982", "Vectrex": "1982",
    "WonderSwan": "1999", "Super_Vision_8000": "1979", "SuperVision": "1992", "SCV": "1984",
    "CreatiVision": "1982", "Casio_PV-1000": "1983", "VC4000": "1978", "AdventureVision": "1982",
    "Gamate": "1990", "AY-3-8500": "1976", "MyVision": "1983", "BBCBridgeCompanion": "1985",
    # computers
    "C64": "1982", "C128": "1985", "C16": "1984", "VIC20": "1980", "PET2001": "1977",
    "Minimig": "1985", "Apple-I": "1976", "Apple-II": "1977", "MacPlus": "1986",
    "ZX-Spectrum": "1982", "ZX81": "1981", "QL": "1984", "ZXNext": "2017", "SAMCoupe": "1989",
    "AcornAtom": "1980", "AcornElectron": "1983", "BBCMicro": "1981", "Archie": "1987",
    "Amstrad": "1984", "Amstrad-PCW": "1985", "Atari800": "1979", "AtariST": "1985",
    "CoCo2": "1983", "CoCo3": "1986", "TRS-80": "1977", "Tandy1000": "1984", "AliceMC10": "1983",
    "PCXT": "1983", "PCjr": "1984", "PDP1": "1959", "VT52": "1975", "SharpMZ": "1978",
    "X68000": "1987", "PC88": "1981", "Ti994a": "1981", "ColecoAdam": "1983", "Aquarius": "1983",
    "TomyTutor": "1982", "Casio_PV-2000": "1983", "SordM5": "1982", "Svi328": "1983",
    "Laser310": "1983", "eg2000": "1982", "RX78": "1983", "TatungEinstein": "1984",
    "Lynx48": "1983", "Oric": "1983", "Jupiter": "1982", "Enterprise": "1985",
    "Interact": "1978", "Altair8800": "1975", "UK101": "1979", "EDSAC": "1949",
    "MSX": "1983", "MSX1": "1983", "TK2000": "1984", "Galaksija": "1983", "Homelab": "1983",
    "Specialist": "1985", "Ondra_SPO186": "1985", "PMD85": "1985", "IQ151": "1985",
    "BK0011M": "1990", "Vector-06C": "1987", "Apogee": "1988", "ORAO": "1984",
    # best-effort years for cores with no single vintage machine: ao486 = i486 era,
    # MultiComp/TSConf = modern FPGA/clone designs (their actual creation year).
    "ao486": "1989", "MultiComp": "2013", "TSConf": "2014",
}

# 2-player link-cable variants ship as separate rbf files but are the same
# hardware (and the same core repo — see CORE_REPO_OVERRIDES) as their base
# handheld, so they'd be duplicate rows. Dropped at export; the base row keeps
# a CORE_NOTES pointer so the variant stays discoverable. GameGear2P is NOT
# here: it's the only standalone Game Gear core (1-player Game Gear is built
# into the SMS core), so its row stays, retitled via SYSTEM_TITLES.
DUPLICATE_VARIANT_CORES = {"Gameboy2P", "GBA2P"}

# Human display titles for console/computer/other rows whose rbf name isn't the
# name a person would use. Keyed by core_name; presentation-only (repo links,
# images and joins all key on the core, not the title). Style rule (user-agreed
# 2026-07-07): use the machine's common name — include the brand only where it's
# part of how people say it (Nintendo 64, Atari ST) and rely on the Manufacturer
# column otherwise (Master System, Vectrex). Cores whose rbf already reads
# naturally (NES, SNES, MSX, Vectrex, X68000, …) are simply absent.
SYSTEM_TITLES = {
    # consoles
    "AdventureVision": "Adventure Vision",
    "Arcadia": "Arcadia 2001",
    "Atari5200": "Atari 5200",
    "Atari7800": "Atari 7800",
    "AtariLynx": "Atari Lynx",
    "BBCBridgeCompanion": "BBC Bridge Companion",
    "Casio_PV-1000": "PV-1000",
    "CDi": "CD-i",
    "ChannelF": "Channel F",
    "GameAndWatch": "Game & Watch (agg23)",
    "GnW": "Game & Watch (GnW)",
    "Gameboy": "Game Boy",
    "GameGear2P": "Game Gear",
    "GBA": "Game Boy Advance",
    "MegaCD": "Mega CD",
    "MegaDrive": "Mega Drive",
    "MyVision": "My Vision",
    "N64": "Nintendo 64",
    "NeoGeo": "Neo Geo",
    "NeoGeoPocket": "Neo Geo Pocket",
    "Odyssey2": "Odyssey 2",
    "PokemonMini": "Pokémon Mini",
    "PSX": "PlayStation",
    "S32X": "32X",
    "SCV": "Super Cassette Vision",
    "SGB": "Super Game Boy",
    "SMS": "Master System",
    "Super_Vision_8000": "Super Vision 8000",
    "SuperVision": "Supervision",
    "TurboGrafx16": "TurboGrafx-16",
    "VC4000": "VC 4000",
    # computers
    "AcornAtom": "Acorn Atom",
    "AcornElectron": "Acorn Electron",
    "AliceMC10": "MC-10 / Alice",
    "Altair8800": "Altair 8800",
    "Amstrad": "Amstrad CPC",
    "Amstrad-PCW": "Amstrad PCW",
    "ao486": "486 PC (ao486)",
    "Apogee": "Apogee BK-01",
    "Apple-I": "Apple I",
    "Apple-II": "Apple II",
    "Archie": "Acorn Archimedes",
    "Atari800": "Atari 800",
    "AtariST": "Atari ST",
    "BBCMicro": "BBC Micro",
    "BK0011M": "BK-0011M",
    "C128": "Commodore 128",
    "C16": "Commodore 16",
    "C64": "Commodore 64",
    "Casio_PV-2000": "PV-2000",
    "CoCo2": "Color Computer 2",
    "CoCo3": "Color Computer 3",
    "ColecoAdam": "Coleco Adam",
    "eg2000": "Colour Genie EG2000",
    "Enterprise": "Enterprise 64/128",
    "IQ151": "IQ 151",
    "Jupiter": "Jupiter Ace",
    "Laser310": "Laser 310",
    "Lynx48": "Camputers Lynx",
    "MacPlus": "Macintosh Plus",
    "Minimig": "Amiga (Minimig)",
    "Ondra_SPO186": "Ondra SPO 186",
    "ORAO": "Orao",
    "PC88": "PC-8801",
    "PCXT": "PC/XT",
    "PDP1": "PDP-1",
    "PET2001": "PET 2001",
    "PMD85": "PMD 85",
    "QL": "Sinclair QL",
    "RX78": "RX-78 Gundam",
    "SAMCoupe": "SAM Coupé",
    "SharpMZ": "Sharp MZ",
    "SordM5": "Sord M5",
    "Svi328": "SV-328",
    "Tandy1000": "Tandy 1000",
    "TatungEinstein": "Tatung Einstein",
    "Ti994a": "TI-99/4A",
    "TomyTutor": "Tomy Tutor",
    "VIC20": "VIC-20",
    "ZX-Spectrum": "ZX Spectrum",
    "ZXNext": "ZX Spectrum Next",
    # other
    "Chip8": "CHIP-8",
    "EpochGalaxyII": "Epoch Galaxy II",
    "FlappyBird": "Flappy Bird",
    "GameOfLife": "Game of Life",
    "TomyScramble": "Tomy Scramble",
}

# Short per-core notes, keyed by core_name (the rbf). Stamped into data.json as
# `note`; the site shows them in the detail panel.
CORE_NOTES = {
    "Gameboy": "A 2-player link-cable variant core (Gameboy2P) is also available.",
    "GBA": "A 2-player link-cable variant core (GBA2P) is also available.",
    "GameGear2P": "This is the 2-player link-cable core; the regular 1-player Game Gear is built into the SMS core.",
    "SMS": "Also plays Game Gear games (a separate 2-player Game Gear core exists).",
}


# Original arcade release years for titles whose MRA carries no <year> and which
# MAME 0.78-era data is too old to cover. The IGS PGM years are MAME-accurate
# (web-verified); the rest are well-documented arcade debut years. Frozen so they
# never drift. Keyed by MAME setname where one exists.
ARCADE_YEAR_BY_SETNAME = {
    "dmnfrnt": "2002",
    "ddp2": "2001", "ddp3": "2002", "dw2001": "2001", "drgw3": "1998", "dwex": "2000",
    "espgal": "2003", "ket": "2003", "kov2": "2000", "kovsh": "1999", "martmast": "1999",
    "orlegend": "1997", "photoy2k": "1999", "svg": "2005", "theglad": "2003",
    "killbld": "1998", "killbldp": "2005", "olds103t": "1998", "sonson": "1984",
}

# Same, for titles with no setname (mostly Coin-Op). Keyed by game name; matched
# via norm_key so region/version suffixes on the catalog title don't matter.
ARCADE_YEAR_BY_NAME = {
    "Space Demon": "1981", "Space Firebird": "1980", "Armed F": "1988",
    "Armed Police Batrider": "1998", "Battle Bakraid - Unlimited Version": "1999",
    "Battle Garegga": "1996", "Chouji Meikyuu Legion": "1987", "Cobra-Command": "1988",
    "Crazy Climber 2": "1984", "Demon's World - Horror Story": "1989", "Gang Wars": "1989",
    "Hachoo": "1989", "Hellfire": "1989", "Hishou Zame": "1987", "Iga Ninjyutsuden": "1988",
    "Ikari III - The Rescue": "1989", "In Your Face": "1991", "Jitsuryoku!! Pro Yakyuu": "1989",
    "Kid no Hore Hore Daisakusen": "1987", "Kozure Ookami": "1987", "Kyukyoku Tiger": "1987",
    "Mahou Daisakusen": "1993", "Mania Challenge": "1986", "Mat Mania": "1985",
    "Out Zone": "1990", "P-47 - The Freedom Fighter": "1990", "P.O.W. - Prisoners of War": "1988",
    "Paddle Mania": "1988", "Pipi & Bibis - Whoopee!!": "1991", "Plus Alpha": "1989",
    "Prehistoric Isle in 1930": "1989", "Psycho-Nics Oscar": "1987",
    "Rally Bike - Dash Yarou": "1988", "Rod-Land": "1990", "SAR - Search And Rescue": "1990",
    "Saint Dragon": "1989", "Same! Same! Same!": "1989", "Sei Senshi Amatelass": "1986",
    "Shippu Mahou Daisakusen": "1994", "Sky Adventure": "1989", "Sky Soldiers": "1988",
    "Snow Bros. - Nick & Tom": "1990", "Snow Bros. 2 - With New Elves - Otenki Paradise": "1992",
    "Soldam": "1992", "Street Smart": "1989", "Tatakae! Big Fighter": "1989",
    "Teenage Mutant Ninja Turtles - Turtles in Time": "1991", "Teki Paki": "1991",
    "Terra Cresta": "1985", "Terra Force": "1987", "The Lord of King": "1989",
    "The Next Space": "1989", "Time Soldiers": "1987", "Truxton - Tatsujin": "1987",
    "Truxton II - Tatsujin Oh": "1992", "Tumble Pop": "1991", "Vimana": "1991",
    "Zero Wing": "1989",
}
_ARCADE_YEAR_BY_NAME_NORM = {norm_key(k): v for k, v in ARCADE_YEAR_BY_NAME.items()}


def arcade_year(setname, title):
    """Frozen original-release year for an arcade title with no MRA <year>."""
    if setname and ARCADE_YEAR_BY_SETNAME.get(setname.lower()):
        return ARCADE_YEAR_BY_SETNAME[setname.lower()]
    return _ARCADE_YEAR_BY_NAME_NORM.get(norm_key(title), "")


def core_build_date(title):
    """Pull a console/computer core's build date from its `_YYYYMMDD` filename suffix.

    Returns an ISO date string (YYYY-MM-DD) or None. This is the core's latest
    build, not a MiSTer debut, so it's kept separate from `release_date`.
    """
    m = _CORE_DATE_RE.search(title or "")
    if not m:
        return None
    y = m.group(1)
    return f"{y[0:4]}-{y[4:6]}-{y[6:8]}"


def _arcade_base(title):
    """Mainline display name: drop trailing (region/rev) and [protection] qualifiers."""
    return re.sub(r"\s*[\(\[].*$", "", title).strip()


# Human-ideal display titles the MAME-description derivation below gets wrong,
# keyed by setname. MAME's canonical name usually wins (it restores the colons,
# punctuation and capitalisation that MRA filenames can't carry), but for these
# sets its choice isn't the name people know, so pin it here.
ARCADE_TITLES = {
    "rallyx": "Rally-X",                   # marquee hyphen; DAT says "Rally X"
    "nrallyx": "New Rally-X",
    "kroozr": "Kozmik Krooz'r",            # DAT drops the apostrophe
    "clubpacm": "Pac-Man Club",            # DAT spells it "Pacman Club"
    "ctsttape": "DECO Test Tape",          # bare "Test Tape" loses all context
    "nspiritj": "Ninja Spirit",            # Japan set; DAT names it "Saigo no Nindou"
    "nomnlnd": "No Man's Land",            # DAT names it "Sengoku no Jieitai"
    "warofbug": "War of the Bugs",         # "...or Monsterous Manouvers in a Mushroom Maze"
    "znpwfv": "Zen Nippon Pro-Wrestling Featuring Virtua",  # DAT truncates "Pro-Wres"
    "cburnrub": "Burnin' Rubber (DECO)",   # cassette version; plain name collides with brubber
    "squash": "Squash (Gaelco 1992)",      # collides with Itisa's 1984 Squash; the MRA's
                                           # qualifier is filename junk (ver + checksum)
    "tetris": "Tetris (Sega System 16)",   # was "(Set 4, Japan, S16A) [FD1094 317-0093]" —
                                           # set number + encryption-chip ID are filename junk
    "tetrisse": "Tetris (Sega System E)",  # sibling of the above; hardware is the real difference
    "darius2": "Darius II",                # was "(Japan, rev 1)"; the dual-screen row is the
                                           # variant, so the single-screen one goes unqualified
    "darius2d": "Darius II (Dual Screen)", # was "(Japan, dual screen, rev 2)"
    "polyplay": "Poly-Play",               # both Poly-Plays share one DAT desc
    "polyplay2": "Poly-Play 2",
}


def _strip_trailing_parens(s):
    """Drop trailing (...) qualifier groups, tolerating nesting: MAME descs like
    'Rompers (Japan, new version (Rev B))' defeat a [^)]* regex."""
    s = s.strip()
    while s.endswith(")"):
        depth, i = 0, len(s) - 1
        while i >= 0:
            if s[i] == ")":
                depth += 1
            elif s[i] == "(":
                depth -= 1
                if depth == 0:
                    break
            i -= 1
        if i < 0:
            break
        s = s[:i].strip()
    return s


def _ideal_arcade_title(raw, sn, arcade_meta):
    """Human-ideal display title for an arcade row, derived from the MAME DAT
    description (which carries the colons/punctuation/caps that MRA filenames
    can't) with the raw MRA-derived name as tie-breaker and fallback.

    Rules, in order: ARCADE_TITLES override; if MAME's bracketed alt name
    ("Chuugokuryuu 2001 [Dragon World 2001]") IS our raw name, the raw
    (Western) name wins; if the whole raw name matches the whole desc, use
    MAME's styling (picking the first name of an "A / B" alt pair); if the
    desc matches a non-first " - "-separated segment of the raw name, the MRA
    crammed alt names together — keep the first (familiar) one; if it matches
    only the first segment, the MRA carries a subtitle MAME lacks — keep raw;
    otherwise MAME's canonical name wins outright. A "(Bootleg)" marker is
    re-added when the raw name carried one, and any existing trailing
    (qualifier) survives verbatim — it's there to disambiguate sibling rows."""
    e = arcade_meta.get((sn or "").lower()) if sn else None
    desc = (e or {}).get("desc") or ""
    if sn in ARCADE_TITLES:
        return ARCADE_TITLES[sn]  # verbatim: pinned titles carry their own qualifier
    m = re.search(r"\s*[\(\[]", raw)
    paren = raw[m.start():].strip() if m else ""
    raw_base = (raw[:m.start()] if m else raw).strip()
    if not desc:
        return raw
    else:
        mame = _strip_trailing_parens(desc)
        bracket = re.search(r"\s*\[([^\]]+)\]", mame)
        if bracket and norm_key(bracket.group(1)) == norm_key(raw_base):
            base = raw_base
        else:
            if bracket:
                mame = mame.replace(bracket.group(0), "").strip()
            first = _strip_trailing_parens(mame.split(" / ")[0]) if " / " in mame else mame
            if norm_key(mame) == norm_key(raw_base):
                base = first
            else:
                segs = [s for s in (x.strip() for x in re.split(r"\s*-\s+", raw_base)) if s]
                hit = next((i for i, s in enumerate(segs)
                            if norm_key(s) in (norm_key(mame), norm_key(first))), None)
                if hit is not None and hit > 0:
                    base = segs[0]
                elif hit == 0 and len(segs) > 1:
                    base = raw_base
                else:
                    base = first
    if "bootleg" in raw_base.lower() and "bootleg" not in base.lower():
        base += " (Bootleg)"
    return (base + (" " + paren if paren else "")).strip()


def _humanize_arcade_titles(data, arcade_meta):
    """Swap every arcade row's title for its human-ideal form. The original
    title moves to `mt` (only when it changed): it stays the join key for the
    image manifest (tools/fetch_images.py matches manifest entries by it) and
    doubles as a hidden search alias, so a discarded alt name ("Puck Man",
    "Green Beret") still finds the row. A rename is skipped when it would
    collide with another row's title — distinct rows must stay distinct."""
    rows = [r for r in data if r.get("base") == "Arcade"]
    proposed = {id(r): _ideal_arcade_title(r["title"], r.get("sn"), arcade_meta)
                for r in rows}
    counts = Counter(proposed.values())
    n = 0
    for r in rows:
        new = proposed[id(r)]
        if new == r["title"] or counts[new] > 1:
            continue
        r["mt"] = r["title"]
        r["title"] = new
        n += 1
    log(f"  humanized {n} arcade titles from MAME descriptions")


def _dat_field(setname, dat, field):
    """A DAT field for a setname, falling back to its parent setname."""
    if not setname or not dat:
        return ""
    sl = setname.lower()
    v = (dat.get(sl) or {}).get(field) or ""
    if v:
        return v
    parent = (dat.get(sl) or {}).get("parent")
    return (dat.get(parent) or {}).get(field) or "" if parent else ""


def _web_row(r, arcade_titles=None, arcade_meta=None, arcade_cats=None, arcade_setnames=None,
             repo_maps=None, arcade_mad=None, dat_desc_index=None, arcade_specs=None):
    """Map a catalog row to the slim record the site renders."""
    system = r["system"]
    base = _BASE_LABEL.get(system, system.title())
    manufacturer = r["manufacturer"] or ""
    sn = ""
    if system == "arcade":
        title = (arcade_titles or {}).get((r["source_id"], r["path"]), r["title"])
        date = (r["release_date"] or "")[:10]
        date_kind = "debut" if date else ""
        # setname for metadata joins: prefer catalog.setname, else the image
        # manifest's resolved setname (backfilled rows have it only there), else
        # recover it by matching the title against the DAT's descriptions — this
        # unlocks year/manufacturer/genre for setname-less rows (coinop/libretro).
        sn = r["setname"] or (arcade_setnames or {}).get(title) or ""
        if not sn and dat_desc_index:
            sn = dat_desc_index.get(_norm_arcade_title(title), "")
        # genre from catver (DB) → catver-by-parent; manufacturer from the MRA
        # (DB) → MAME DAT by setname → by parent. Fills the clone-setname genre
        # gaps and the Toaplan/Nichibutsu/UPL manufacturer gaps.
        genre = r["genre"] or genre_for(sn, arcade_cats or {}, arcade_meta or {})
        if not manufacturer:
            manufacturer = _dat_field(sn, arcade_meta, "manufacturer")
        # the FPGA core (rbf) the game runs on. Multi-game cores (jtcps2, ST-V,
        # Neogeo, …) are why many titles share one MiSTer date — surfacing it
        # explains/disambiguates those clumps. Blank for the ~58 setname-less
        # Toaplan/SNK titles whose catalog row never captured an rbf.
        core = (r["rbf"] or "").strip()
    else:
        # the Core column shows (and links) the core name for non-arcade rows too
        core = core_name(r["title"])
        # cores: strip the date suffix from the display name (date has its own
        # column), then swap in the human title where the rbf name isn't one
        title = SYSTEM_TITLES.get(core, _CORE_DATE_RE.sub("", r["title"]).rstrip("_ "))
        # prefer the real MiSTer debut (per-core repo) over the build-date suffix
        debut = (r["release_date"] or "")[:10]
        if debut:
            date, date_kind = debut, "debut"
        else:
            date = core_build_date(r["title"]) or ""
            date_kind = "build" if date else ""
        genre = ""
        cn = core_name(r["title"])
        if not manufacturer:
            if system == "console":
                manufacturer = CONSOLE_MANUFACTURER.get(cn, "")
            elif system == "computer":
                manufacturer = COMPUTER_MANUFACTURER.get(cn, "")
    year = r["year"] or ""
    if not year and system in ("console", "computer"):
        year = CORE_YEAR.get(core_name(r["title"]), "")
    if not year and system == "arcade":
        year = arcade_year(sn, title) or _dat_field(sn, arcade_meta, "year")
    # the core's latest commit date (its most recent update). `date` above is the
    # MiSTer *debut* (first commit); this is the newest build. Shown in its own
    # sortable column so a years-old debut date doesn't imply the core is stale.
    updated = (r["last_update"] or "")[:10] if "last_update" in r.keys() else ""
    repo = _repo_for(r, core, repo_maps or {})
    row = {
        "title": title,
        "base": base,
        "genre": genre,
        "date": date,
        "date_kind": date_kind,
        "year": year,
        "manufacturer": manufacturer,
        "core": core,
        "deprecated": False,
    }
    # updated == date just means "never touched since debut" — still worth a cell
    if updated:
        row["updated"] = updated
    if repo:
        row["repo"] = repo
    # system rows only: arcade rows share rbfs with these (System E games run on
    # the SMS core), and a console-flavoured note is wrong on a game row. If a
    # per-arcade-core note ever lands (e.g. jts18 CRT sync), give it its own dict.
    if system != "arcade" and core in CORE_NOTES:
        row["note"] = CORE_NOTES[core]
    if system == "arcade":
        # the row's own MAME setname ("ROM name"). Distinct from the screenshot
        # key (img), which can be a shared/borrowed setname.
        if sn:
            row["sn"] = sn
        # MAD metadata (rotation/resolution/players/controls/flip), display-ready
        row.update(mad_for(sn, arcade_mad or {}, arcade_meta or {}))
        # provisional fill for cells MAD hasn't catalogued yet: mame2003-plus
        # supplies rotation/players/controls/special for brand-new titles. MAD
        # always wins (we only fill blanks); `prov` flags these for gray display
        # and they self-heal — once MAD has the value, the cell is no longer
        # blank so no provisional fill happens.
        sp = specs_for(sn, arcade_specs or {}, arcade_meta or {})
        prov = [k for k in ("rot", "plr", "ctl", "spc")
                if not row.get(k) and sp.get(k)]
        for k in prov:
            row[k] = sp[k]
        if prov:
            row["prov"] = prov
    return row


# Rows the repo resolvers can't reach, keyed by lowercase core/rbf: cores whose
# repo doesn't follow the MiSTer-devel/<core>_MiSTer naming the crawls expect
# (so catalog.repo stayed empty), multi-game arcade cores with no Arcade-<rbf>
# repo, and third-party cores. Pinned in code, same philosophy as the
# frozen-date maps; hand-verified against GitHub.
FROZEN_REPOS = {
    "st-v": "MiSTer-devel/Saturn_MiSTer",          # ST-V rbf is built from the Saturn repo
    "sms": "MiSTer-devel/SMS_MiSTer",              # Sega System E arcade rows run on the SMS core
    "jtngp": "jotego/jtcores/tree/master/cores/ngp",
    "neogeopocket": "jotego/jtcores/tree/master/cores/ngp",
    "skysmasher": "rmonic79/Arcade_SkySmasher_MiSTer",  # third-party, no MiSTer-devel repo
    "atari5200": "MiSTer-devel/Atari800_MiSTer",   # 5200 rbf is built from the Atari800 repo
    "intellivision": "MiSTer-devel/Intv_MiSTer",
    "ay-3-8500": "MiSTer-devel/AY-3-8500-MiSTer",
    "scv": "MiSTer-devel/SuperCassetteVision_MiSTer",
    "epochgalaxyii": "MiSTer-devel/EpochGalaxy2_MiSTer",
    "samcoupe": "MiSTer-devel/SAM-Coupe_MiSTer",
    "ondra_spo186": "MiSTer-devel/OndraSPO186_MiSTer",
    "homelab": "MiSTer-devel/Homelab-MiSTer",
}
# Arcade rows whose catalog row has no rbf at all (pre-enrich rows); the live
# MRAs declare the rbf, hand-resolved here by exact catalog title.
FROZEN_TITLE_REPOS = {
    "Flash Boy (DECO)": "MiSTer-devel/Arcade-DECOCassette_MiSTer",
    "Ocean to Ocean (DECO)": "MiSTer-devel/Arcade-DECOCassette_MiSTer",
    "Space Demon": "MiSTer-devel/Arcade-SpaceFirebird_MiSTer",
}


def _repo_for(r, core, repo_maps):
    """GitHub path (after github.com/) for a catalog row's core repo, or ''.

    catalog.repo (set by the DB snapshot / repo crawls) wins; arcade rows it
    missed fall back on the rbf: Jotego rbfs deep-link into the jtcores
    monorepo, others match arcade_repos by core name, then the frozen maps.
    """
    repo = (r["repo"] or "").strip() if "repo" in r.keys() else ""
    if repo:
        # catalog stores Jotego rows as 'jotego/jtcores (cores/<x>)' — turn the
        # display form into a browsable monorepo path
        m = re.fullmatch(r"(\S+) \((\S+)\)", repo)
        return f"{m.group(1)}/tree/master/{m.group(2)}" if m else repo
    lc = (core or "").lower()
    if lc:
        folder = (repo_maps.get("jt") or {}).get(lc)
        if folder:
            return f"jotego/jtcores/tree/master/cores/{folder}"
        repo = (repo_maps.get("arcade") or {}).get(lc)
        if repo:
            return repo
        if lc in FROZEN_REPOS:
            return FROZEN_REPOS[lc]
    return FROZEN_TITLE_REPOS.get((r["title"] or "").strip(), "")


# Cores no longer in any current DB but worth showing for the record. The Sega
# Genesis core was retired and replaced by the MegaDrive core (same console);
# dates from its archived repo (MiSTer-devel/Genesis_MiSTer, earliest..last rbf).
EXTRA_WEB_ROWS = [
    {
        "title": "Genesis", "base": "Console", "genre": "",
        "date": "2018-06-02", "date_kind": "debut", "year": "1988",
        "manufacturer": "Sega", "core": "Genesis", "deprecated": True,
        "repo": "MiSTer-devel/Genesis_MiSTer",
    },
]


def cmd_export_web(args):
    con = connect()
    # The site lives at /releases (Pages still serves from docs/); the docs root
    # just redirects there so the bare URL keeps working.
    outdir = DOCSDIR / "releases"
    outdir.mkdir(parents=True, exist_ok=True)
    apply_frozen_core_dates(con)  # always pin hand-verified core debuts before publishing
    apply_frozen_arcade_core_dates(con)  # and repo-less multi-game arcade cores
    apply_jt_frozen_dates(con)  # correct Jotego cores off the Feb-2023 monorepo-migration date
    con.commit()
    rows = con.execute("SELECT * FROM catalog").fetchall()
    # repo-link fallbacks for arcade rows whose catalog.repo is empty: Jotego
    # rbf -> jtcores monorepo folder, and rbf -> arcade_repos by core name
    # (arcade_repos.core is 'Arcade-<Name>'; the rbf is usually '<name>').
    repo_maps = {
        "jt": {("jt" + f[0]).lower() if not (f[1] or "").strip() else f[1].strip().lower(): f[0]
               for f in con.execute("SELECT folder, rbf FROM jt_cores")},
        "arcade": {(c or "").lower().replace("arcade-", "", 1): repo
                   for repo, c in con.execute("SELECT repo, core FROM arcade_repos")},
    }
    con.close()
    # Drop arcade region/revision/bootleg variants (MiSTer files them under
    # _Arcade/_alternatives/); the site shows only the mainline title per game.
    rows = [r for r in rows if not (
        r["system"] == "arcade" and "/_alternatives/" in r["path"].replace("\\", "/"))]
    # Drop arcade BIOS/placeholder rows that aren't games (e.g. the IGS PGM BIOS,
    # which has no year/screenshot and just clutters the list).
    rows = [r for r in rows if not (
        r["system"] == "arcade" and (r["setname"] or "").lower() in ARCADE_EXCLUDE_SETNAMES)]
    # Drop 2-player link-cable duplicates of handhelds already listed 1-player.
    rows = [r for r in rows if not (
        r["kind"] == "core" and core_name(r["title"]) in DUPLICATE_VARIANT_CORES)]
    # arcade fill sources (cached; no-op if absent): DAT for year/manufacturer/
    # parent, catver for genre, and the image manifest's resolved setnames (many
    # backfilled rows carry a setname only there, not in catalog.setname).
    arcade_meta = load_arcade_dat_meta()
    arcade_cats = local_catver()
    arcade_setnames = load_manifest_setnames()
    arcade_mad = local_mad()
    # provisional specs (rotation/players/controls) for rows MAD hasn't reached
    arcade_specs = local_specs()
    # reverse index for rows with no setname anywhere: recover it from the title
    dat_desc_index = build_dat_desc_index(arcade_meta)
    # Display the clean mainline name, but keep the qualifier where the stripped
    # base name collides among kept rows (genuinely distinct hardware/publisher
    # versions that share a base, e.g. Kangaroo / Kangaroo (Atari) / (Bootleg)).
    counts = Counter(_arcade_base(r["title"]) for r in rows if r["system"] == "arcade")
    arcade_titles = {}
    for r in rows:
        if r["system"] == "arcade":
            b = _arcade_base(r["title"])
            arcade_titles[(r["source_id"], r["path"])] = b if counts[b] == 1 else r["title"]
    data = [_web_row(r, arcade_titles, arcade_meta, arcade_cats, arcade_setnames, repo_maps,
                     arcade_mad, dat_desc_index, arcade_specs) for r in rows]
    # Human-ideal arcade titles (colons, punctuation, one name per game) from
    # the MAME descs. Must run AFTER _web_row — the setname/genre/screenshot
    # joins above all key on the raw MRA-derived title.
    _humanize_arcade_titles(data, arcade_meta)
    data.extend(EXTRA_WEB_ROWS)
    # sort: arcade first by date then title, cores after; keep it stable/predictable
    data.sort(key=lambda d: (d["base"], d["date"] or "9999", d["title"].lower()))
    (outdir / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # NOTE: outdir/index.html is a hand-maintained static page and the single
    # source of truth. export-web deliberately does NOT regenerate it — it used
    # to write a duplicate copy of the HTML kept in a Python constant, which
    # kept silently reverting front-end edits on the next export. The page is
    # fully data-driven (fetches data.json at runtime), so only data.json needs
    # regenerating.
    (DOCSDIR / "index.html").write_text(ROOT_REDIRECT_HTML, encoding="utf-8")
    _backfill_libretro_images(data)  # give brand-new arcade titles a libretro shot
    _retag_image_dims()  # re-apply img/img_w/img_h that regenerating data.json drops
    _write_site_meta(outdir)  # last-updated stamp, bumped only when data.json changes
    log(f"web export written to {outdir}")
    log(f"  data.json: {len(data)} rows")
    by_base = {}
    for d in data:
        by_base[d["base"]] = by_base.get(d["base"], 0) + 1
    log(f"  by type: {by_base}")
    log(f"  arcade with genre: {sum(1 for d in data if d['genre'])}")
    norepo = [d for d in data if not d.get("repo")]
    log(f"  repo link: {len(data) - len(norepo)} resolved, {len(norepo)} without")
    if norepo:
        sample = ", ".join(f"{d['title']} [{d['core'] or '-'}]" for d in norepo[:8])
        log(f"    e.g. {sample}")
    n_rot = sum(1 for d in data if d.get("rot"))
    n_prov = sum(1 for d in data if d.get("prov"))
    log(f"  arcade with rotation: {n_rot}/{by_base.get('Arcade', 0)} "
        f"({n_prov} rows carry provisional specs)")


def _write_site_meta(outdir):
    """Write releases/meta.json with a 'last updated' timestamp that advances
    ONLY when the served data.json content actually changes. We hash the final
    data.json bytes (after the image re-tag) and compare to the hash recorded on
    the previous export; if identical, we keep the old timestamp so re-running
    the pipeline with no real change doesn't move the displayed date/time."""
    data_path = outdir / "data.json"
    meta_path = outdir / "meta.json"
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    prev = {}
    if meta_path.exists():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    if prev.get("hash") == digest and prev.get("updated"):
        updated = prev["updated"]
    else:
        updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    meta_path.write_text(
        json.dumps({"updated": updated, "hash": digest}), encoding="utf-8")
    log(f"  meta.json: updated={updated} ({'unchanged' if prev.get('hash') == digest else 'bumped'})")


LIBRETRO_RAW = "https://raw.githubusercontent.com/libretro-thumbnails/MAME/master/{}"
LIBRETRO_TREE_API = "/repos/libretro-thumbnails/MAME/git/trees/master?recursive=1"


def _libretro_slug(s):
    """The on-disk image key for a title. MUST match tools/fetch_images.py slug()
    so the re-tag step (which recomputes it) finds the PNG we just saved."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _fetch_libretro_png(ref, dest):
    """Download one libretro thumbnail (ref like 'Named_Titles/Dig Dug.png') to
    dest. Returns True on a valid PNG. Skips if a non-empty file is already there."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    url = LIBRETRO_RAW.format(urllib.parse.quote(ref))
    try:
        body = http_get(url)
    except Exception as e:
        log(f"    libretro miss {ref}: {e}")
        return False
    if not body or body[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return True


def _backfill_libretro_images(data):
    """Give arcade titles that debuted since the last manifest build a screenshot
    from libretro-thumbnails (per-file GitHub raw — CI-friendly: no 7z, no giant
    progettoSNAPS packs, no MAME DAT).

    Native-res progettoSNAPS remains a manual local pass; this just stops brand-new
    titles from landing on the daily site with no image. Each candidate is recorded
    in the manifest exactly once (with refs if matched, empty if not) so it's never
    re-resolved, and the following _retag_image_dims() stamps the refs onto data.json.
    A later local build_manifest run rebuilds the whole manifest and upgrades any of
    these to native-res progettoSNAPS where available."""
    manifest_path = CACHEDIR / "image_manifest.json"
    if not manifest_path.exists():
        return  # no manifest to extend (cold checkout); nothing to do
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return
    # manifest entries are keyed by the raw MRA-derived title, which a
    # humanized row keeps in `mt` — always match/record with that form
    known = {e["title"] for e in manifest}
    todo = [r for r in data
            if r.get("base") == "Arcade" and not r.get("deprecated")
            and (r.get("mt") or r["title"]) not in known]
    if not todo:
        return  # steady state: no new titles since the last manifest build

    # The repo file tree, fetched once (cached; gitignored so re-fetched per CI run).
    tree_path = CACHEDIR / "libretro_mame_tree.json"
    if tree_path.exists():
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    else:
        try:
            tree = gh_api(LIBRETRO_TREE_API)
            CACHEDIR.mkdir(parents=True, exist_ok=True)
            tree_path.write_text(json.dumps(tree), encoding="utf-8")
        except Exception as e:
            log(f"  libretro backfill skipped: tree fetch failed ({e})")
            return

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import match  # normalization + region-aware candidate picking
    except Exception as e:
        log(f"  libretro backfill skipped: match module unavailable ({e})")
        return
    idx = {f: match.build_index(tree, f) for f in ("Named_Titles", "Named_Snaps")}

    hits = 0
    for r in todo:
        title = r.get("mt") or r["title"]
        res = match.resolve(title, idx)  # {folder: filename stem or None}
        entry = {"title": title, "setname": None, "source": None,
                 "title_img": None, "snap_img": None,
                 "third_img": None, "third_pack": None}
        got = False
        for folder, field, slot in (("Named_Titles", "title_img", "title"),
                                    ("Named_Snaps", "snap_img", "snap")):
            stem = res.get(folder)
            if not stem:
                continue
            ref = f"{folder}/{stem}.png"
            dest = DOCSDIR / "images" / slot / (_libretro_slug(title) + ".png")
            if _fetch_libretro_png(ref, dest):
                entry[field] = ref
                entry["source"] = "libretro"
                got = True
        if got:
            hits += 1
        manifest.append(entry)  # record even misses so they aren't re-resolved

    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                             encoding="utf-8")
    log(f"  libretro backfill: {hits}/{len(todo)} new arcade titles matched a screenshot")


def _retag_image_dims():
    """Re-apply the self-hosted screenshot keys (img / img_slots / img_w / img_h)
    that live only in data.json and are dropped every time export-web regenerates
    it. Runs tools/fetch_images.py in re-tag mode (no downloads, no 7z: it just
    reads the cached manifest + the PNG headers already on disk). Guarded so a
    checkout without the image cache still exports cleanly."""
    tool = ROOT / "tools" / "fetch_images.py"
    manifest = CACHEDIR / "image_manifest.json"
    if not (tool.exists() and manifest.exists()):
        log("  (skipping image re-tag: tools/fetch_images.py or manifest missing)")
        return
    try:
        subprocess.run([sys.executable, str(tool), "data"], check=True)
    except Exception as e:
        log(f"  WARNING: image re-tag failed ({e}); data.json has no screenshot keys")


ROOT_REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>misterzine</title>
<link rel="canonical" href="./releases/">
<meta http-equiv="refresh" content="0; url=./releases/">
</head>
<body><p>Redirecting to <a href="./releases/">releases</a> &hellip;</p></body>
</html>
"""


# --- command: stats -------------------------------------------------------

def cmd_stats(args):
    con = connect()
    def q1(sql, *p):
        r = con.execute(sql, p).fetchone()
        return r[0] if r else 0
    print("=== misterzine database ===")
    print(f"db: {DBPATH}")
    print()
    print("Sources:")
    for r in con.execute("SELECT * FROM sources").fetchall():
        print(f"  {r['name']:<22} ts={r['last_timestamp_iso']}  fetched={r['last_fetch']}")
    print()
    print(f"Catalog rows (release units): {q1('SELECT COUNT(*) FROM catalog')}")
    for r in con.execute("SELECT system, COUNT(*) c FROM catalog GROUP BY system ORDER BY c DESC"):
        print(f"  {r['system']:<10} {r['c']}")
    print()
    dated = q1("SELECT COUNT(*) FROM catalog WHERE system='arcade' AND release_date IS NOT NULL")
    print(f"Arcade titles with a real release date: {dated}")
    print("  date sources:")
    for label, like in [("MiSTer-devel repos", "MiSTer-devel%"),
                        ("Jotego jtcores", "jotego%"),
                        ("Coin-Op commits", "Coin-Op%")]:
        n = q1("SELECT COUNT(*) FROM catalog WHERE system='arcade' AND release_date IS NOT NULL AND repo LIKE ?", like)
        print(f"    {label:<20} {n}")
    print(f"Retrospective inputs: {q1('SELECT COUNT(*) FROM arcade_repos')} MiSTer-devel repos, "
          f"{q1('SELECT COUNT(*) FROM jt_cores')} Jotego cores, "
          f"{q1('SELECT COUNT(*) FROM coinop_releases')} Coin-Op releases")
    er = con.execute("SELECT MIN(first_commit), MAX(last_commit) FROM arcade_repos").fetchone()
    print(f"  MiSTer-devel date span: {(er[0] or '?')[:10]} .. {(er[1] or '?')[:10]}")
    print()
    print(f"Dated events logged: {q1('SELECT COUNT(*) FROM events')}")
    for r in con.execute("SELECT event_type, COUNT(*) c FROM events GROUP BY event_type"):
        print(f"  {r['event_type']:<10} {r['c']}")
    print()
    print("Most recent arcade debuts (from repo history):")
    for r in con.execute("SELECT core, first_commit FROM arcade_repos ORDER BY first_commit DESC LIMIT 8"):
        print(f"  {(r['first_commit'] or '?')[:10]}  {r['core']}")
    con.close()


# --- command: build (catalog + snapshot, optionally repos) ----------------

def cmd_build(args):
    cmd_snapshot(args)
    if args.with_repos:
        cmd_repos(args)
        cmd_core_repos(args)
        cmd_jtcores(args)
        cmd_coinop(args)
        cmd_enrich_mra(args)   # year/manufacturer/rbf/setname from MRA XML (clones repos)
    cmd_genre(args)            # arcade genre from cached catver + DAT parent fallback (offline)
    cmd_mad(args)              # arcade metadata (rotation/players/controls) from MAD
    cmd_specs(args)            # provisional specs (mame2003-plus) for rows not yet in MAD
    cmd_export(args)
    cmd_export_web(args)       # also re-tags screenshot dims via _retag_image_dims()
    cmd_stats(args)


def main():
    ap = argparse.ArgumentParser(description="misterzine release database")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="fetch DBs, diff vs last snapshot, log dated events")
    sp.set_defaults(func=cmd_snapshot)

    rp = sub.add_parser("repos", help="crawl per-core arcade repos for real release dates")
    rp.add_argument("--limit", type=int, default=0, help="limit number of repos (testing)")
    rp.add_argument("--force", action="store_true", help="re-crawl even repos not pushed since last crawl")
    rp.set_defaults(func=cmd_repos)

    crp = sub.add_parser("core-repos", help="crawl console/computer/other per-core repos for debut dates")
    crp.add_argument("--limit", type=int, default=0, help="limit number of repos (testing)")
    crp.add_argument("--force", action="store_true", help="re-crawl even repos not pushed since last crawl")
    crp.set_defaults(func=cmd_core_repos)

    mp = sub.add_parser("enrich-mra", help="add year/manufacturer/rbf from MRA XML")
    mp.set_defaults(func=cmd_enrich_mra)

    jp = sub.add_parser("jtcores", help="backfill Jotego release dates from jtcores monorepo")
    jp.add_argument("--limit", type=int, default=0)
    jp.add_argument("--force", action="store_true", help="re-crawl even if the monorepo wasn't pushed since last crawl")
    jp.set_defaults(func=cmd_jtcores)

    cp = sub.add_parser("coinop", help="backfill Coin-Op release dates from develop commit messages")
    cp.set_defaults(func=cmd_coinop)

    gp = sub.add_parser("genre", help="add arcade genre from MAME catver.ini (joined on setname)")
    gp.set_defaults(func=cmd_genre)

    mp = sub.add_parser("mad", help="fetch arcade metadata (rotation/players/controls) from the MiSTer Arcade Database")
    mp.set_defaults(func=cmd_mad)

    spp = sub.add_parser("specs", help="fetch provisional arcade specs (mame2003-plus) for rows not yet in MAD")
    spp.set_defaults(func=cmd_specs)

    mmp = sub.add_parser("mame-meta", help="derive committed mame_meta.json.gz from the local raw MAME DAT (local pass)")
    mmp.set_defaults(func=cmd_mame_meta)

    ep = sub.add_parser("export", help="write JSON/JSONL exports from the db")
    ep.set_defaults(func=cmd_export)

    wp = sub.add_parser("export-web", help="write the static site (docs/) for GitHub Pages")
    wp.set_defaults(func=cmd_export_web)

    stp = sub.add_parser("stats", help="print database summary")
    stp.set_defaults(func=cmd_stats)

    bp = sub.add_parser("build", help="snapshot + export + stats (add --with-repos for dates)")
    bp.add_argument("--with-repos", action="store_true", help="also crawl repos for release dates")
    bp.add_argument("--limit", type=int, default=0)
    bp.set_defaults(func=cmd_build)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
