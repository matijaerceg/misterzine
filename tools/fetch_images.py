"""Build the self-hosted image set.

For progettoSNAPS-sourced rows: download each referenced pack zip once, pull the
inner .7z, and extract only our setnames' PNGs. For libretro-fallback rows:
fetch the named files directly. Output goes to docs/images/{title,snap,ingame}/
keyed by a stable slug, and image keys are written back into data.json.

Stdlib + 7z.exe. Re-runnable: downloaded zips and existing outputs are skipped.
"""
import json, os, re, struct, subprocess, sys, urllib.request, urllib.parse, zipfile, shutil

try:  # certifi when available: local trust stores can be too old for the
    import ssl  # modern Let's Encrypt chain that adb.arcadeitalia.net uses
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data/cache/image_manifest.json")
DATA = os.path.join(ROOT, "docs/releases/data.json")
ZIPDIR = os.path.join(ROOT, "data/cache/psnaps_zips")
IMGROOT = os.path.join(ROOT, "docs/images")
SEVENZIP = r"C:\Program Files\7-Zip\7z.exe"
UA = {"User-Agent": "Mozilla/5.0 misterzine-build"}

PS_BASE = "https://www.progettosnaps.net/snapshots/packs/full_sets/"
PS_ZIP = {  # pack -> outer zip filename
    "titles": "pS_titles_fullset_287.zip", "snap": "pS_snap_fullset_287.zip",
    "gameover": "pS_gameover_fullset_270.zip", "scores": "pS_scores_fullset_270.zip",
    "select": "pS_select_fullset_270.zip", "bosses": "pS_bosses_fullset_270.zip",
    "howto": "pS_howto_fullset_270.zip", "versus": "pS_versus_fullset_270.zip",
}
LIBRETRO_RAW = "https://raw.githubusercontent.com/libretro-thumbnails/MAME/master/{}"
# which output dir each pack feeds
SLOT = {"titles": "title", "snap": "snap", "gameover": "ingame", "scores": "ingame",
        "select": "ingame", "bosses": "ingame", "howto": "ingame", "versus": "ingame"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def png_dims(path):
    """(width, height) from a PNG's IHDR header, or None if unreadable."""
    try:
        with open(path, "rb") as f:
            f.read(16)  # 8-byte signature + 4-byte length + 'IHDR'
            return struct.unpack(">II", f.read(8))
    except Exception:
        return None


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        total = int(r.headers.get("Content-Length", 0)); got = 0
        with open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b); got += len(b)
                if total:
                    sys.stdout.write(f"\r    {os.path.basename(path)}: {got/1e6:6.0f}/{total/1e6:.0f} MB"); sys.stdout.flush()
    print()
    os.replace(tmp, path)
    return path


def inner_7z(zip_path, dest_dir):
    """Extract the single inner .7z from an outer pack zip; return its path."""
    with zipfile.ZipFile(zip_path) as z:
        member = next(n for n in z.namelist() if n.lower().endswith(".7z"))
        out = os.path.join(dest_dir, os.path.basename(member))
        if not (os.path.exists(out) and os.path.getsize(out) > 0):
            with z.open(member) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    return out


def extract_pngs(seven_path, names, out_dir):
    """Extract only `names` (e.g. {'dkong.png'}) flat into out_dir via listfile."""
    os.makedirs(out_dir, exist_ok=True)
    listfile = seven_path + ".list"
    with open(listfile, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(names)))
    subprocess.run([SEVENZIP, "e", seven_path, f"-o{out_dir}", f"@{listfile}",
                    "-y", "-aoa"], check=True, stdout=subprocess.DEVNULL)
    os.remove(listfile)


def do_psnaps(manifest, only_pack=None):
    """Resolve {pack: {setname}} from manifest and extract. only_pack limits work."""
    need = {}  # pack -> set(setname)
    for e in manifest:
        if e["source"] != "psnaps":
            continue
        for field in ("title_img", "snap_img", "third_img"):
            ref = e[field]
            if ref:
                pack, fn = ref.split("/", 1)
                need.setdefault(pack, set()).add(fn[:-4])  # strip .png
    os.makedirs(ZIPDIR, exist_ok=True)
    for pack, sets in need.items():
        if only_pack and pack != only_pack:
            continue
        print(f"[{pack}] {len(sets)} images -> docs/images/{SLOT[pack]}/")
        zip_path = download(PS_BASE + PS_ZIP[pack], os.path.join(ZIPDIR, PS_ZIP[pack]))
        seven = inner_7z(zip_path, ZIPDIR)
        out_dir = os.path.join(IMGROOT, SLOT[pack])
        extract_pngs(seven, {s + ".png" for s in sets}, out_dir)
        n = sum(1 for s in sets if os.path.exists(os.path.join(out_dir, s + ".png")))
        print(f"    extracted {n}/{len(sets)}")
        os.remove(seven)  # reclaim disk; outer zip kept for re-runs


def do_libretro(manifest):
    for e in manifest:
        if e["source"] != "libretro":
            continue
        key = slug(e["title"])
        for field, sub in (("title_img", "title"), ("snap_img", "snap")):
            ref = e[field]
            if not ref:
                continue
            out = os.path.join(IMGROOT, sub, key + ".png")
            if os.path.exists(out):
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            url = LIBRETRO_RAW.format(urllib.parse.quote(ref))
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
                open(out, "wb").write(data)
            except Exception as ex:
                print(f"    libretro miss {e['title']}: {ex}")


def do_adb(manifest):
    """Re-fetch Arcade Database screenshots for adb-sourced entries whose PNGs
    are missing on disk (they're normally saved by the CI backfill itself).
    ADB 404s non-browser requests: needs the UA + Referer below."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/126.0 Safari/537.36",
               "Referer": "https://adb.arcadeitalia.net/"}
    for e in manifest:
        if e["source"] != "adb":
            continue
        for field, sub in (("title_img", "title"), ("snap_img", "snap")):
            ref = e[field]
            if not ref:
                continue
            out = os.path.join(IMGROOT, sub, e["setname"] + ".png")
            if os.path.exists(out):
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            url = "https://adb.arcadeitalia.net/media/mame.current/" + ref
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                              timeout=60, context=SSL_CONTEXT).read()
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    open(out, "wb").write(data)
            except Exception as ex:
                print(f"    adb miss {e['title']}: {ex}")


def update_data(manifest):
    by_title = {e["title"]: e for e in manifest}
    rows = json.load(open(DATA, encoding="utf-8"))
    for r in rows:
        # humanized rows keep their raw MRA-derived title (the manifest key) in mt
        e = by_title.get(r.get("mt") or r.get("title"))
        if not e or r.get("base") != "Arcade":
            continue
        # psnaps and adb images are saved keyed by setname; libretro/manual by slug
        key = e["setname"] if e["source"] in ("psnaps", "adb") else slug(e["title"])
        slots = [s for s, f in (("title", "title_img"), ("snap", "snap_img"),
                                ("ingame", "third_img")) if e[f]]
        if slots:
            r["img"] = key
            r["img_slots"] = slots
            # all slots of a game share one native resolution; tag w/h so the
            # popup can integer-scale and size itself before the PNG loads.
            for s in slots:
                d = png_dims(os.path.join(IMGROOT, s, key + ".png"))
                if d:
                    r["img_w"], r["img_h"] = int(d[0]), int(d[1])
                    break
    json.dump(rows, open(DATA, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    print(f"data.json updated: {sum(1 for r in rows if r.get('img'))} rows tagged, "
          f"{sum(1 for r in rows if r.get('img_w'))} with dims")


def main():
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        do_psnaps(manifest)
        do_libretro(manifest)
        do_adb(manifest)
        update_data(manifest)
    elif arg.startswith("pack="):
        do_psnaps(manifest, only_pack=arg.split("=", 1)[1])
    elif arg == "libretro":
        do_libretro(manifest)
    elif arg == "adb":
        do_adb(manifest)
    elif arg == "data":
        update_data(manifest)


if __name__ == "__main__":
    main()
