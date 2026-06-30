"""Validate the fetch+self-host pipeline on a small sample.

Picks the best candidate filename per title, downloads Title/Snap/Boxart from
libretro-thumbnails raw, stores under data/cache/sample_images/, and validates
each PNG (reads IHDR for dimensions). Stdlib only.
"""
import json, re, struct, urllib.parse, urllib.request, os
from collections import defaultdict
from probe_images import norm, build_index, TREE

RAW = "https://raw.githubusercontent.com/libretro-thumbnails/MAME/master/{folder}/{name}.png"
OUT = "data/cache/sample_images"
FOLDERS = ["Named_Titles", "Named_Snaps", "Named_Boxarts"]
SAMPLE = ["Defender", "Colony 7", "1942", "Donkey Kong", "Galaga",
          "Bubble Bobble", "Out Run", "Pac-Man"]


def pick(cands):
    """Prefer World > USA > World/USA-agnostic shortest name."""
    def score(n):
        low = n.lower()
        return (0 if "world" in low else 1 if "usa" in low else 2, len(n))
    return sorted(cands, key=score)[0]


def png_dims(b):
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", b[16:24])
    return w, h


def main():
    tree = json.load(open(TREE, encoding="utf-8"))
    idx = {f: build_index(tree, f) for f in FOLDERS}
    os.makedirs(OUT, exist_ok=True)
    for title in SAMPLE:
        key = norm(title)
        print(f"\n{title}  (norm={key!r})")
        for f in FOLDERS:
            cands = idx[f].get(key)
            if not cands:
                print(f"  {f:14s}: --- no candidate")
                continue
            name = pick(cands)
            url = RAW.format(folder=f, name=urllib.parse.quote(name))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "misterzine-probe"})
                data = urllib.request.urlopen(req, timeout=30).read()
                dims = png_dims(data)
                safe = re.sub(r"[^A-Za-z0-9]+", "_", title)
                path = f"{OUT}/{safe}__{f}.png"
                open(path, "wb").write(data)
                print(f"  {f:14s}: OK {len(data):6d}B {dims}  <- {name}")
            except Exception as e:
                print(f"  {f:14s}: ERR {type(e).__name__} {e}  ({name})")


if __name__ == "__main__":
    main()
