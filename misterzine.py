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
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error
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
        try:
            _token_cache = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        except Exception:
            _token_cache = ""
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
    """Download a db.json.zip, return (timestamp, {path: {hash,size}})."""
    log(f"  fetching {source['name']} ...")
    raw = http_get(source["db_url"])
    z = zipfile.ZipFile(BytesIO(raw))
    inner = z.read(z.namelist()[0])
    d = json.loads(inner)
    files = {}
    for path, meta in d.get("files", {}).items():
        files[path] = {"hash": meta.get("hash"), "size": meta.get("size")}
    return d.get("timestamp"), files


def latest_snapshot(source_id):
    sd = SNAPDIR / source_id
    if not sd.exists():
        return None
    snaps = sorted(sd.glob("*.json"))
    if not snaps:
        return None
    return json.loads(snaps[-1].read_text(encoding="utf-8"))


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
        ts, files = fetch_db(source)
        prev = latest_snapshot(source["id"])
        ts_iso = epoch_to_iso(ts) or now_iso()

        con.execute(
            "INSERT INTO sources(id,name,db_url,last_timestamp,last_timestamp_iso,last_fetch) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "last_timestamp=excluded.last_timestamp, last_timestamp_iso=excluded.last_timestamp_iso, "
            "last_fetch=excluded.last_fetch",
            (source["id"], source["name"], source["db_url"], ts, ts_iso, now_iso()),
        )

        seed = prev is None
        events = []
        old_files = prev["files"] if prev else {}

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

        # removals (only meaningful after seed)
        if not seed:
            for path in old_files:
                if path not in files:
                    system, kind, is_unit = classify(path)
                    if not is_unit:
                        continue
                    events.append((ts_iso, source["id"], path, title_from_path(path), system, "removed", None))

        # upsert catalog rows for everything currently present
        upsert_catalog(con, source["id"], files, ts_iso, seed)

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
            con.execute(
                "INSERT INTO catalog(source_id,path,system,kind,title,hash,size,first_seen,last_seen,last_changed) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (source_id, path, system, kind, title, meta.get("hash"), meta.get("size"),
                 ts_iso, ts_iso, ts_iso),
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

def list_arcade_repos():
    repos = []
    page = 1
    while True:
        data, hdrs = gh_api(
            f"/orgs/{ARCADE_REPO_ORG}/repos?per_page=100&page={page}&type=public", want_headers=True
        )
        if not data:
            break
        for r in data:
            if r["name"].startswith(ARCADE_REPO_PREFIX) and not r.get("archived", False):
                repos.append(r)
        link = hdrs.get("Link", "")
        if 'rel="next"' not in link:
            break
        page += 1
    return repos


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
    for i, r in enumerate(repos, 1):
        full = r["full_name"]
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
    hit = miss = 0
    for i, base in enumerate(bases, 1):
        full = f"{ARCADE_REPO_ORG}/{base}_MiSTer"
        try:
            first, last, count = repo_commit_bounds(full)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                miss += 1
                log(f"  [{i}/{len(bases)}] {full}: no repo (404)")
                continue
            log(f"  [{i}/{len(bases)}] {full}: ERROR {e}")
            continue
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
        subprocess.run(["git", "-C", str(repodir), "pull", "--ff-only"], check=False)
    return repodir


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
    """Attach Jotego dates to arcade catalog rows whose rbf is jt<folder>."""
    jt = {r["folder"]: r for r in con.execute("SELECT * FROM jt_cores").fetchall()}
    n = 0
    for row in con.execute(
        "SELECT source_id, path, rbf, release_date FROM catalog "
        "WHERE system='arcade' AND rbf IS NOT NULL AND release_date IS NULL"
    ).fetchall():
        rbf = row["rbf"].lower()
        folder = rbf[2:] if rbf.startswith("jt") else rbf
        r = jt.get(folder)
        if r:
            debut = JT_CORE_FROZEN_DATES.get(folder, r["first_commit"])
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (JT_REPO + f" (cores/{folder})", debut, r["last_commit"],
                 row["source_id"], row["path"]),
            )
            n += 1
    log(f"  joined {n} Jotego arcade titles to release dates")


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


def cmd_genre(args):
    con = connect()
    cats = parse_catver(fetch_catver())
    log(f"genre: {len(cats)} setname->genre entries from catver.ini")
    rows = con.execute(
        "SELECT source_id, path, setname FROM catalog WHERE system='arcade' AND setname IS NOT NULL"
    ).fetchall()
    n = 0
    for row in rows:
        g = cats.get(row["setname"].lower())
        if g:
            con.execute(
                "UPDATE catalog SET genre=? WHERE source_id=? AND path=?",
                (g, row["source_id"], row["path"]),
            )
            n += 1
    con.commit()
    con.close()
    log(f"  joined {n}/{len(rows)} arcade titles (with a setname) to a genre")


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
    "Battle Garegga": "1996", "Chouji Meikyuu Legion": "1987", "Cobra-Command": "1984",
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


def _web_row(r, arcade_titles=None):
    """Map a catalog row to the slim record the site renders."""
    system = r["system"]
    base = _BASE_LABEL.get(system, system.title())
    manufacturer = r["manufacturer"] or ""
    if system == "arcade":
        title = (arcade_titles or {}).get((r["source_id"], r["path"]), r["title"])
        date = (r["release_date"] or "")[:10]
        date_kind = "debut" if date else ""
        genre = r["genre"] or ""
    else:
        # cores: strip the date suffix from the display name (date has its own column)
        title = _CORE_DATE_RE.sub("", r["title"]).rstrip("_ ")
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
        year = arcade_year(r["setname"], title)
    return {
        "title": title,
        "base": base,
        "genre": genre,
        "date": date,
        "date_kind": date_kind,
        "year": year,
        "manufacturer": manufacturer,
        "deprecated": False,
    }


# Cores no longer in any current DB but worth showing for the record. The Sega
# Genesis core was retired and replaced by the MegaDrive core (same console);
# dates from its archived repo (MiSTer-devel/Genesis_MiSTer, earliest..last rbf).
EXTRA_WEB_ROWS = [
    {
        "title": "Genesis", "base": "Console", "genre": "",
        "date": "2018-06-02", "date_kind": "debut", "year": "1988",
        "manufacturer": "Sega", "deprecated": True,
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
    con.close()
    # Drop arcade region/revision/bootleg variants (MiSTer files them under
    # _Arcade/_alternatives/); the site shows only the mainline title per game.
    rows = [r for r in rows if not (
        r["system"] == "arcade" and "/_alternatives/" in r["path"].replace("\\", "/"))]
    # Display the clean mainline name, but keep the qualifier where the stripped
    # base name collides among kept rows (genuinely distinct hardware/publisher
    # versions that share a base, e.g. Kangaroo / Kangaroo (Atari) / (Bootleg)).
    counts = Counter(_arcade_base(r["title"]) for r in rows if r["system"] == "arcade")
    arcade_titles = {}
    for r in rows:
        if r["system"] == "arcade":
            b = _arcade_base(r["title"])
            arcade_titles[(r["source_id"], r["path"])] = b if counts[b] == 1 else r["title"]
    data = [_web_row(r, arcade_titles) for r in rows]
    data.extend(EXTRA_WEB_ROWS)
    # sort: arcade first by date then title, cores after; keep it stable/predictable
    data.sort(key=lambda d: (d["base"], d["date"] or "9999", d["title"].lower()))
    (outdir / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (outdir / "index.html").write_text(SITE_HTML, encoding="utf-8")
    (DOCSDIR / "index.html").write_text(ROOT_REDIRECT_HTML, encoding="utf-8")
    log(f"web export written to {outdir}")
    log(f"  data.json: {len(data)} rows")
    by_base = {}
    for d in data:
        by_base[d["base"]] = by_base.get(d["base"], 0) + 1
    log(f"  by type: {by_base}")
    log(f"  arcade with genre: {sum(1 for d in data if d['genre'])}")


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


SITE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>misterzine — MiSTer FPGA core &amp; title index</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font: 14px/1.4 system-ui, sans-serif; margin: 0; padding: 1rem; }
  header { margin-bottom: .75rem; }
  h1 { font-size: 1.25rem; margin: 0 0 .25rem; }
  .legend { color: #888; font-size: .8rem; margin: .25rem 0 0; }
  .controls { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin: .75rem 0; }
  input[type=search] { padding: .4rem .6rem; min-width: 16rem; flex: 1; }
  select, input[type=search] { font-size: .9rem; border: 1px solid #8884; border-radius: 4px; background: transparent; color: inherit; }
  select { padding: .4rem; }
  .count { color: #888; font-size: .8rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #8883; vertical-align: top; }
  th { position: sticky; top: 0; background: Canvas; cursor: pointer; user-select: none; white-space: nowrap; }
  th[aria-sort=ascending]::after { content: " \\2191"; }
  th[aria-sort=descending]::after { content: " \\2193"; }
  td.type { white-space: nowrap; color: #06c; }
  td.date { white-space: nowrap; font-variant-numeric: tabular-nums; }
  tr:hover td { background: #8881; }
  .build { color: #888; }
  /* screenshot popup — right-docked, vertically centered card (bottom-docked on mobile) */
  .shot { cursor: zoom-in; border-bottom: 1px dotted #8886; }
  #popup { position: fixed; z-index: 50; display: none;
           right: 16px; top: 50%; transform: translateY(-50%);
           max-width: min(42vw, 576px); padding: .5rem; background: Canvas;
           border: 1px solid #8888; border-radius: 6px; box-shadow: 0 6px 24px #0007; }
  #popup .shots { display: flex; gap: .5rem; justify-content: center; }
  #popup.stacked .shots { flex-direction: column; align-items: center; }
  #popup img { image-rendering: pixelated; background: #000;
               border-radius: 3px; display: block; }  /* w/h set inline by JS */
  #popup .cap { margin-top: .4rem; font-size: .8rem; color: #888; text-align: center; }
  @media (max-width: 640px) {
    /* bottom-docked so it never crowds the (also narrow) title column */
    #popup { right: 8px; left: 8px; top: auto; bottom: 8px; transform: none; max-width: none; }
  }
</style>
</head>
<body>
<header>
  <h1>misterzine — MiSTer FPGA core &amp; title index</h1>
  <p class="legend">MiSTer release date = core's MiSTer debut where known, otherwise its latest
    build date (<span class="build">grey</span>). Original Year = the real hardware's release year.
    Genre via MAME catver.ini.</p>
</header>
<div class="controls">
  <input type="search" id="q" placeholder="Search title, type, manufacturer…" autofocus>
  <select id="type">
    <option value="">All types</option>
    <option value="Arcade">Arcade</option>
    <option value="Console">Console</option>
    <option value="Computer">Computer</option>
    <option value="Other">Other</option>
  </select>
  <span class="count" id="count"></span>
</div>
<table>
  <thead><tr>
    <th data-k="title">Title</th>
    <th data-k="typesort">Type</th>
    <th data-k="date">MiSTer release date</th>
    <th data-k="year">Original Year</th>
    <th data-k="manufacturer">Manufacturer</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<div id="popup"></div>
<script>
let DATA = [], view = [], sortKey = 'date', sortDir = -1;  // default: most recent first

function typeLabel(d) {
  if (d.base === 'Arcade') return d.genre ? 'Arcade, ' + d.genre : 'Arcade';
  return d.base + ' core' + (d.deprecated ? ' (deprecated)' : '');
}

function titleCell(d) {
  if (!d.img) return esc(d.title);
  const cap = d.title + (d.year ? ' (' + d.year + ')' : '') +
    (d.manufacturer ? ' — ' + d.manufacturer : '') + (d.genre ? ' • ' + d.genre : '');
  return '<span class="shot" data-img="' + escA(d.img) + '" data-slots="' +
    d.img_slots.join(',') + '" data-w="' + (d.img_w || '') + '" data-h="' + (d.img_h || '') +
    '" data-cap="' + escA(cap) + '">' + esc(d.title) + '</span>';
}

function render() {
  const tb = document.getElementById('rows');
  tb.innerHTML = view.map(d =>
    '<tr><td>' + titleCell(d) + '</td>' +
    '<td class="type">' + esc(typeLabel(d)) + '</td>' +
    '<td class="date' + (d.date_kind === 'build' ? ' build' : '') + '">' + esc(d.date) + '</td>' +
    '<td>' + esc(d.year) + '</td>' +
    '<td>' + esc(d.manufacturer) + '</td></tr>'
  ).join('');
  document.getElementById('count').textContent = view.length + ' of ' + DATA.length;
}

function esc(s) { return (s || '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function escA(s) { return esc(s).replace(/"/g, '&quot;'); }

function apply() {
  const q = document.getElementById('q').value.toLowerCase().trim();
  const t = document.getElementById('type').value;
  view = DATA.filter(d => {
    if (t && d.base !== t) return false;
    if (!q) return true;
    return (d.title + ' ' + typeLabel(d) + ' ' + d.manufacturer + ' ' + d.year).toLowerCase().includes(q);
  });
  if (sortKey) {
    view.sort((a, b) => {
      const av = sortKey === 'typesort' ? typeLabel(a) : (a[sortKey] || '');
      const bv = sortKey === 'typesort' ? typeLabel(b) : (b[sortKey] || '');
      return av < bv ? -sortDir : av > bv ? sortDir : 0;
    });
  }
  render();
}

document.getElementById('q').addEventListener('input', apply);
document.getElementById('type').addEventListener('change', apply);
document.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
  const k = th.dataset.k;
  sortDir = (sortKey === k) ? -sortDir : 1;
  sortKey = k;
  document.querySelectorAll('th').forEach(o => o.removeAttribute('aria-sort'));
  th.setAttribute('aria-sort', sortDir === 1 ? 'ascending' : 'descending');
  apply();
}));

// --- screenshot popup (hover on desktop, tap-to-pin on touch) ---
const pop = document.getElementById('popup');
const rowsEl = document.getElementById('rows');
let pinned = false, showT, hideT;

// --- sizing: pick side-by-side vs stacked, whichever makes the two shots bigger ---
const PAD = 8, GAP = 8, CAPH = 26;  // card padding, inter-shot gap, caption strip

function box() {  // content box the shots must fit inside; capped + margined so titles stay clear
  if (innerWidth <= 640)
    return { w: innerWidth - 16 - 2 * PAD, h: Math.round(0.42 * innerHeight) - 2 * PAD - CAPH };
  return { w: Math.min(0.42 * innerWidth, 560) - 2 * PAD,
           h: Math.min(0.78 * innerHeight, 680) - 2 * PAD - CAPH };
}

function layout(nw, nh, n) {
  const b = box();
  if (n <= 1) { const s = Math.min(b.w / nw, b.h / nh);
    return { stacked: false, w: Math.round(nw * s), h: Math.round(nh * s) }; }
  const sSide = Math.min((b.w - GAP) / (2 * nw), b.h / nh);   // two across
  const sStack = Math.min(b.w / nw, (b.h - GAP) / (2 * nh));  // two down
  const stacked = sStack > sSide, s = Math.max(sSide, sStack);
  return { stacked, w: Math.max(1, Math.round(nw * s)), h: Math.max(1, Math.round(nh * s)) };
}

// --- loading: decode every shot before revealing, so the card never flickers in ---
const decoded = new Set();
function loadImg(src) {
  if (decoded.has(src)) { const im = new Image(); im.src = src; return Promise.resolve(im); }
  const im = new Image(); im.src = src;
  return im.decode().then(() => { decoded.add(src); return im; }).catch(() => null);
}
function shotSrcs(el) {  // title + gameplay only (drop the game-over/state shot)
  const img = el.dataset.img;
  return el.dataset.slots.split(',').filter(s => s === 'title' || s === 'snap')
    .map(s => '../images/' + s + '/' + img + '.png');
}
function prefetch(el) { shotSrcs(el).forEach(loadImg); }  // warm cache on hover-intent

let token = 0;
async function showPop(el) {
  clearTimeout(hideT);
  const my = ++token;
  const imgs = (await Promise.all(shotSrcs(el).map(loadImg))).filter(Boolean);
  if (my !== token || !imgs.length) return;  // superseded by a newer hover, or all missing
  const nw = +el.dataset.w || imgs[0].naturalWidth;
  const nh = +el.dataset.h || imgs[0].naturalHeight;
  const lay = layout(nw, nh, imgs.length);
  pop.classList.toggle('stacked', lay.stacked);
  pop.innerHTML = '<div class="shots">' +
    imgs.map(im => '<img width="' + lay.w + '" height="' + lay.h + '" src="' + im.src + '">').join('') +
    '</div><div class="cap">' + esc(el.dataset.cap) + '</div>';
  pop.style.display = 'block';
}
function hidePop() { token++; pop.style.display = 'none'; }  // bump token to cancel a pending reveal

rowsEl.addEventListener('mouseover', e => {
  const el = e.target.closest('.shot'); if (!el || pinned) return;
  prefetch(el);
  clearTimeout(hideT); clearTimeout(showT);
  showT = setTimeout(() => showPop(el), 140);
});
rowsEl.addEventListener('mouseout', e => {
  if (pinned || !e.target.closest('.shot')) return;
  clearTimeout(showT); hideT = setTimeout(hidePop, 120);
});
rowsEl.addEventListener('click', e => {
  const el = e.target.closest('.shot'); if (!el) return;
  e.preventDefault(); pinned = true; showPop(el);
});
pop.addEventListener('mouseover', () => { if (!pinned) clearTimeout(hideT); });
pop.addEventListener('mouseout', () => { if (!pinned) hideT = setTimeout(hidePop, 120); });
document.addEventListener('click', e => {
  if (pinned && !e.target.closest('.shot') && !e.target.closest('#popup')) { pinned = false; hidePop(); }
});
window.addEventListener('scroll', () => { if (!pinned) hidePop(); }, true);

fetch('./data.json').then(r => r.json()).then(d => {
  DATA = d;
  const th = document.querySelector('th[data-k="date"]');
  if (th) th.setAttribute('aria-sort', sortDir === 1 ? 'ascending' : 'descending');
  apply();
});
</script>
</body>
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
    cmd_export(args)
    cmd_export_web(args)
    cmd_stats(args)


def main():
    ap = argparse.ArgumentParser(description="misterzine release database")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="fetch DBs, diff vs last snapshot, log dated events")
    sp.set_defaults(func=cmd_snapshot)

    rp = sub.add_parser("repos", help="crawl per-core arcade repos for real release dates")
    rp.add_argument("--limit", type=int, default=0, help="limit number of repos (testing)")
    rp.set_defaults(func=cmd_repos)

    crp = sub.add_parser("core-repos", help="crawl console/computer/other per-core repos for debut dates")
    crp.add_argument("--limit", type=int, default=0, help="limit number of repos (testing)")
    crp.set_defaults(func=cmd_core_repos)

    mp = sub.add_parser("enrich-mra", help="add year/manufacturer/rbf from MRA XML")
    mp.set_defaults(func=cmd_enrich_mra)

    jp = sub.add_parser("jtcores", help="backfill Jotego release dates from jtcores monorepo")
    jp.add_argument("--limit", type=int, default=0)
    jp.set_defaults(func=cmd_jtcores)

    cp = sub.add_parser("coinop", help="backfill Coin-Op release dates from develop commit messages")
    cp.set_defaults(func=cmd_coinop)

    gp = sub.add_parser("genre", help="add arcade genre from MAME catver.ini (joined on setname)")
    gp.set_defaults(func=cmd_genre)

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
