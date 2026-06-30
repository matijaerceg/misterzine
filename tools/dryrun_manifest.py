"""Dry run: resolve title+snap filenames for every arcade title, write a
manifest, and report match rate. Downloads nothing."""
import json
from match import load, resolve, title_keys, FOLDERS

OUT = "data/cache/image_manifest.json"
SPOTCHECK = ["Pac-Man", "Bubble Bobble", "Galaga 3 - Gaplus", "TankBattalion",
             "Rush'n Attack - Green Beret", "Donkey Kong", "Out Run"]


def main():
    arc, idx = load()
    manifest, both, any_hit, miss = [], 0, 0, []
    for r in arc:
        res = resolve(r["title"], idx)
        t, s = res["Named_Titles"], res["Named_Snaps"]
        if t and s:
            both += 1
        if t or s:
            any_hit += 1
        else:
            miss.append(r["title"])
        manifest.append({"title": r["title"], "title_file": t, "snap_file": s})
    json.dump(manifest, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    n = len(arc)
    print(f"arcade titles: {n}")
    print(f"  title+snap both: {both} ({100*both/n:.1f}%)")
    print(f"  any image      : {any_hit} ({100*any_hit/n:.1f}%)")
    print(f"  misses         : {len(miss)}\n")
    print("spot-check picks:")
    for title in SPOTCHECK:
        res = resolve(title, idx)
        print(f"  {title!r} keys={title_keys(title)}")
        print(f"      title -> {res['Named_Titles']}")
        print(f"      snap  -> {res['Named_Snaps']}")
    print("\nremaining misses:")
    for m in miss:
        print("   -", m)


if __name__ == "__main__":
    main()
