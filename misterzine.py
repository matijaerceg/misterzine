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
    con.commit()
    con.close()
    log("repos crawl done.")


def join_repos_to_catalog(con):
    """Attach repo release dates to arcade catalog rows.

    Match priority: the MRA <rbf> core name (most reliable), then the title.
    """
    repos = con.execute("SELECT repo, core, first_commit, last_commit FROM arcade_repos").fetchall()
    by_key = {}
    for r in repos:
        key = norm_key(r["core"].replace("Arcade-", ""))
        by_key.setdefault(key, r)  # first wins
    n = 0
    for row in con.execute(
        "SELECT source_id, path, title, rbf FROM catalog WHERE system='arcade'"
    ).fetchall():
        r = None
        if row["rbf"]:
            r = by_key.get(norm_key(row["rbf"]))
        if r is None:
            r = by_key.get(norm_key(row["title"]))
        if r:
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (r["repo"], r["first_commit"], r["last_commit"], row["source_id"], row["path"]),
            )
            n += 1
    log(f"  joined {n} arcade titles to a core repo (release dates attached)")


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
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (JT_REPO + f" (cores/{folder})", r["first_commit"], r["last_commit"],
                 row["source_id"], row["path"]),
            )
            n += 1
    log(f"  joined {n} Jotego arcade titles to release dates")


# --- command: coinop (Coin-Op release dates from commit messages) ---------

COINOP_REPO = "Coin-OpCollection/Distribution-MiSTerFPGA"
COINOP_RE = re.compile(r"^(.+?)\s+Release\s+(\d{8})", re.IGNORECASE)


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
                title = m.group(1).strip()
                ymd = m.group(2)
                rel_date = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
                cdate = c["commit"]["committer"]["date"]
                # keep the most recent commit per title
                if title not in found or cdate > found[title][1]:
                    found[title] = (rel_date, cdate)
        if 'rel="next"' not in hdrs.get("Link", ""):
            break
        page += 1
    for title, (rel_date, cdate) in found.items():
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


def join_coinop_to_catalog(con):
    """Attach Coin-Op release dates to coinop catalog titles by normalized prefix."""
    rels = con.execute("SELECT title, release_date, commit_date FROM coinop_releases").fetchall()
    # index by normalized key; release titles are the short/canonical form
    by_key = {norm_key(r["title"]): r for r in rels}
    n = 0
    for row in con.execute(
        "SELECT source_id, path, title FROM catalog WHERE source_id='coinop'"
    ).fetchall():
        ck = norm_key(row["title"])
        match = None
        for rk, r in by_key.items():
            if ck == rk or ck.startswith(rk):  # "snowbrosnicktom" startswith "snowbros"
                match = r
                break
        if match:
            con.execute(
                "UPDATE catalog SET repo=?, release_date=?, last_update=? WHERE source_id=? AND path=?",
                (COINOP_REPO, match["release_date"], match["commit_date"],
                 row["source_id"], row["path"]),
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


def _web_row(r):
    """Map a catalog row to the slim record the site renders."""
    system = r["system"]
    base = _BASE_LABEL.get(system, system.title())
    if system == "arcade":
        title = r["title"]
        date = (r["release_date"] or "")[:10]
        date_kind = "debut" if date else ""
        genre = r["genre"] or ""
    else:
        # cores: strip the date suffix from the display name (date has its own column)
        title = _CORE_DATE_RE.sub("", r["title"]).rstrip("_ ")
        date = core_build_date(r["title"]) or ""
        date_kind = "build" if date else ""
        genre = ""
    return {
        "title": title,
        "base": base,
        "genre": genre,
        "date": date,
        "date_kind": date_kind,
        "year": r["year"] or "",
        "manufacturer": r["manufacturer"] or "",
    }


def cmd_export_web(args):
    con = connect()
    DOCSDIR.mkdir(parents=True, exist_ok=True)
    rows = con.execute("SELECT * FROM catalog").fetchall()
    con.close()
    data = [_web_row(r) for r in rows]
    # sort: arcade first by date then title, cores after; keep it stable/predictable
    data.sort(key=lambda d: (d["base"], d["date"] or "9999", d["title"].lower()))
    (DOCSDIR / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (DOCSDIR / "index.html").write_text(SITE_HTML, encoding="utf-8")
    log(f"web export written to {DOCSDIR}")
    log(f"  data.json: {len(data)} rows")
    by_base = {}
    for d in data:
        by_base[d["base"]] = by_base.get(d["base"], 0) + 1
    log(f"  by type: {by_base}")
    log(f"  arcade with genre: {sum(1 for d in data if d['genre'])}")


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
</style>
</head>
<body>
<header>
  <h1>misterzine — MiSTer FPGA core &amp; title index</h1>
  <p class="legend">Date = MiSTer debut where known, otherwise the core's latest build date
    (<span class="build">grey</span>). Genre via MAME catver.ini.</p>
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
    <th data-k="date">Date</th>
    <th data-k="year">Year</th>
    <th data-k="manufacturer">Manufacturer</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
let DATA = [], view = [], sortKey = null, sortDir = 1;

function typeLabel(d) {
  if (d.base === 'Arcade') return d.genre ? 'Arcade, ' + d.genre : 'Arcade';
  return d.base + ' core';
}

function render() {
  const tb = document.getElementById('rows');
  tb.innerHTML = view.map(d =>
    '<tr><td>' + esc(d.title) + '</td>' +
    '<td class="type">' + esc(typeLabel(d)) + '</td>' +
    '<td class="date' + (d.date_kind === 'build' ? ' build' : '') + '">' + esc(d.date) + '</td>' +
    '<td>' + esc(d.year) + '</td>' +
    '<td>' + esc(d.manufacturer) + '</td></tr>'
  ).join('');
  document.getElementById('count').textContent = view.length + ' of ' + DATA.length;
}

function esc(s) { return (s || '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

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

fetch('./data.json').then(r => r.json()).then(d => { DATA = d; view = d; render(); });
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

    rp = sub.add_parser("repos", help="crawl per-core repos for real release dates")
    rp.add_argument("--limit", type=int, default=0, help="limit number of repos (testing)")
    rp.set_defaults(func=cmd_repos)

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
