"""Build the self-hosted image set.

For progettoSNAPS-sourced rows: download each referenced pack zip once, pull the
inner .7z, and extract only our setnames' PNGs. For libretro-fallback rows:
fetch the named files directly. Output goes to docs/images/{title,snap,ingame}/
keyed by a stable slug, and image keys are written back into data.json.

Stdlib + 7z.exe. Re-runnable: downloaded zips and existing outputs are skipped.
"""
import json, os, re, subprocess, sys, urllib.request, urllib.parse, zipfile, shutil

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


def update_data(manifest):
    by_title = {e["title"]: e for e in manifest}
    rows = json.load(open(DATA, encoding="utf-8"))
    for r in rows:
        e = by_title.get(r.get("title"))
        if not e or r.get("base") != "Arcade":
            continue
        key = e["setname"] if e["source"] == "psnaps" else slug(e["title"])
        slots = [s for s, f in (("title", "title_img"), ("snap", "snap_img"),
                                ("ingame", "third_img")) if e[f]]
        if slots:
            r["img"] = key
            r["img_slots"] = slots
    json.dump(rows, open(DATA, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    print(f"data.json updated: {sum(1 for r in rows if r.get('img'))} rows tagged")


def main():
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        do_psnaps(manifest)
        do_libretro(manifest)
        update_data(manifest)
    elif arg.startswith("pack="):
        do_psnaps(manifest, only_pack=arg.split("=", 1)[1])
    elif arg == "libretro":
        do_libretro(manifest)
    elif arg == "data":
        update_data(manifest)


if __name__ == "__main__":
    main()
