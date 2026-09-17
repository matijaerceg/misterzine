"""Seed the image service's R2 bucket (images.misterzine.fyi) from progettoSNAPS.

The MisterZine frontend asks images.misterzine.fyi/snap/<setname>.png for
arcade games the catalogue does not list. This one-time (and occasional
re-run) step puts the whole progettoSNAPS snap and title sets in R2, keyed by
setname, so the Worker almost never has to fetch anything at request time.

    python tools/seed_r2.py --meta                      # meta/parent.json, meta/desc.json from mame_meta
    python tools/seed_r2.py --pack snap --pack titles   # the full packs (~1.2 GB, 80k+ objects each)
    python tools/seed_r2.py --also-site                 # docs/images/{snap,title} keys R2 lacks
    python tools/seed_r2.py --pack snap --force         # after a pack version bump: re-upload changed bytes
    python tools/seed_r2.py --purge-negatives           # forget remembered misses after a re-seed

Credentials come from the environment: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY (an R2 API token scoped to the bucket, Object Read &
Write), or from .secrets/r2.json with the same keys. boto3 and 7-Zip are
needed locally only; nothing here runs in CI.
"""
import argparse
import concurrent.futures
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from fetch_images import PS_BASE, PS_ZIP, SEVENZIP, ZIPDIR, download, inner_7z, png_dims  # noqa: E402

BUCKET = "misterzine-images"
STAGE = os.path.join(ROOT, "data", "cache", "r2_stage")
MAME_META = os.path.join(ROOT, "data", "cache", "mame_meta.json.gz")
SUMMARY = os.path.join(ROOT, "data", "cache", "r2_seed.json")
SETNAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
PACK_KIND = {"snap": "snap", "titles": "title"}  # pack -> R2 prefix (the Worker's route)


def setname_of(filename):
    """The R2 key stem for a pack file, or None when it is not a setname."""
    stem, ext = os.path.splitext(os.path.basename(filename))
    if ext.lower() != ".png" or not SETNAME_RE.match(stem):
        return None
    return stem


def meta_maps(meta):
    """(parent map, description map) from mame_meta's {setname: {parent, desc}}."""
    parents = {k: v["parent"] for k, v in meta.items() if v.get("parent") and v["parent"] != k}
    descs = {k: v["desc"] for k, v in meta.items() if v.get("desc")}
    return parents, descs


def plan_uploads(files, existing, force=False):
    """Which (key, path) pairs to send: new keys, or all of them under --force."""
    out = []
    for key, path in files:
        if force or key not in existing:
            out.append((key, path))
    return out


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- R2 ------------------------------------------------------------------------

def credentials():
    keys = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    creds = {k: os.environ.get(k) for k in keys}
    if not all(creds.values()):
        p = os.path.join(ROOT, ".secrets", "r2.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                creds.update({k: v for k, v in json.load(f).items() if k in keys})
    missing = [k for k, v in creds.items() if not v]
    if missing:
        sys.exit("missing R2 credentials: " + ", ".join(missing))
    return creds


def client():
    import boto3  # local-only dependency
    c = credentials()
    return boto3.client(
        "s3", endpoint_url=f"https://{c['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=c["R2_ACCESS_KEY_ID"], aws_secret_access_key=c["R2_SECRET_ACCESS_KEY"],
        region_name="auto")


def list_keys(s3, prefix):
    """{key: etag} for every object under prefix."""
    out = {}
    token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"]] = o["ETag"].strip('"')
        if not r.get("IsTruncated"):
            return out
        token = r.get("NextContinuationToken")


def put_png(s3, key, path, src):
    dims = png_dims(path)
    if not dims:
        return "rejected"
    s3.put_object(Bucket=BUCKET, Key=key, Body=open(path, "rb"), ContentType="image/png",
                  Metadata={"w": str(dims[0]), "h": str(dims[1]), "src": src,
                            "seeded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    return "uploaded"


def upload_many(s3, items, src, workers, dry_run, existing=None):
    """items: [(key, path)]. Skips identical bytes when existing holds etags."""
    counts = {"uploaded": 0, "skipped": 0, "rejected": 0}
    todo = []
    for key, path in items:
        if existing is not None and key in existing and existing[key] == md5_of(path):
            counts["skipped"] += 1
            continue
        todo.append((key, path))
    if dry_run:
        counts["uploaded"] = len(todo)
        return counts
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for i, result in enumerate(ex.map(lambda kp: put_png(s3, kp[0], kp[1], src), todo), 1):
            counts[result] += 1
            if i % 500 == 0:
                print(f"    {i}/{len(todo)}", flush=True)
    return counts


# --- steps ------------------------------------------------------------------------

def stage_pack(pack):
    """Extract the whole pack under data/cache/r2_stage/<pack>/; return [(key, path)]."""
    os.makedirs(ZIPDIR, exist_ok=True)
    zip_path = download(PS_BASE + PS_ZIP[pack], os.path.join(ZIPDIR, PS_ZIP[pack]))
    seven = inner_7z(zip_path, ZIPDIR)
    out_dir = os.path.join(STAGE, pack)
    os.makedirs(out_dir, exist_ok=True)
    # -aos keeps files already extracted, so an interrupted run resumes.
    subprocess.run([SEVENZIP, "e", seven, f"-o{out_dir}", "-y", "-aos"], check=True, stdout=subprocess.DEVNULL)
    files = []
    for name in sorted(os.listdir(out_dir)):
        sn = setname_of(name)
        if sn:
            files.append((f"{PACK_KIND[pack]}/{sn}.png", os.path.join(out_dir, name)))
    return files


def site_files(kind):
    """docs/images/<kind>/*.png as (key, path) pairs for setname-shaped stems."""
    d = os.path.join(ROOT, "docs", "images", kind)
    out = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        stem, ext = os.path.splitext(name)
        if ext.lower() == ".png" and SETNAME_RE.match(stem):
            out.append((f"{kind}/{stem}.png", os.path.join(d, name)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack", action="append", choices=sorted(PACK_KIND), default=[])
    ap.add_argument("--meta", action="store_true", help="upload meta/parent.json and meta/desc.json")
    ap.add_argument("--also-site", action="store_true", help="upload docs/images snap/title keys R2 lacks")
    ap.add_argument("--only-mame", action="store_true", help="limit packs to setnames mame_meta knows")
    ap.add_argument("--limit", type=int, default=0, help="stop after N files per pack (smoke test)")
    ap.add_argument("--force", action="store_true", help="re-send files whose bytes changed")
    ap.add_argument("--purge-negatives", action="store_true", help="delete every neg/ marker")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if not (a.pack or a.meta or a.also_site or a.purge_negatives):
        ap.error("nothing to do")

    s3 = None if a.dry_run else client()
    summary = {}
    if os.path.exists(SUMMARY):
        with open(SUMMARY, encoding="utf-8") as f:
            summary = json.load(f)
    meta = None
    if a.meta or a.only_mame:
        with gzip.open(MAME_META, "rt", encoding="utf-8") as f:
            meta = json.load(f)

    if a.meta:
        parents, descs = meta_maps(meta)
        print(f"meta: {len(parents)} parents, {len(descs)} descriptions")
        if not a.dry_run:
            s3.put_object(Bucket=BUCKET, Key="meta/parent.json", Body=json.dumps(parents, separators=(",", ":")), ContentType="application/json")
            s3.put_object(Bucket=BUCKET, Key="meta/desc.json", Body=json.dumps(descs, ensure_ascii=False, separators=(",", ":")), ContentType="application/json")
        summary["meta"] = {"parents": len(parents), "descs": len(descs)}

    for pack in a.pack:
        kind = PACK_KIND[pack]
        print(f"[{pack}] staging {PS_ZIP[pack]}")
        files = stage_pack(pack)
        if a.only_mame:
            files = [(k, p) for k, p in files if os.path.basename(p)[:-4] in meta]
        if a.limit:
            files = files[:a.limit]
        existing = {} if a.dry_run else list_keys(s3, kind + "/")
        todo = plan_uploads(files, existing, a.force)
        print(f"[{pack}] {len(files)} files, {len(existing)} already in R2, {len(todo)} to check")
        counts = upload_many(s3, todo, "psnaps" + re.sub(r"\D", "", PS_ZIP[pack]), a.workers, a.dry_run,
                             existing if a.force else None)
        print(f"[{pack}] {counts}")
        summary[kind] = {"pack": PS_ZIP[pack], "files": len(files), **counts,
                         "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

    if a.also_site:
        for kind in ("snap", "title"):
            files = site_files(kind)
            existing = {} if a.dry_run else list_keys(s3, kind + "/")
            todo = plan_uploads(files, existing)
            counts = upload_many(s3, todo, "site", a.workers, a.dry_run)
            print(f"[site {kind}] {len(files)} files, {counts}")
            summary.setdefault("site", {})[kind] = counts

    if a.purge_negatives and not a.dry_run:
        keys = list(list_keys(s3, "neg/"))
        for i in range(0, len(keys), 1000):
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]]})
        print(f"purged {len(keys)} negative markers")

    summary["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not a.dry_run:
        s3.put_object(Bucket=BUCKET, Key="meta/seed.json", Body=json.dumps(summary, indent=1), ContentType="application/json")
        os.makedirs(os.path.dirname(SUMMARY), exist_ok=True)
        with open(SUMMARY, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1)
            f.write("\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
