"""Probe libretro-thumbnails/MAME match rate for our arcade titles.

Reads the cached repo tree (data/cache/libretro_mame_tree.json) and the site
data (docs/releases/data.json), then reports how many arcade titles can be
matched to a Title / Snap / Boxart image. Pure measurement; downloads nothing.
"""
import json, re, sys
from collections import defaultdict

TREE = "data/cache/libretro_mame_tree.json"
DATA = "docs/releases/data.json"

PAREN = re.compile(r"\([^()]*\)")


def norm(s):
    """Normalize a name for fuzzy matching."""
    s = s.lower()
    # libretro encodes & * / : ` < > ? \ | as underscore; treat _ as separator
    s = s.replace("_", " ")
    # drop region/version qualifiers: (Japan), (World, set 1), ...
    prev = None
    while prev != s:
        prev = s
        s = PAREN.sub(" ", s)
    # move trailing ", the"/", a" article to front-agnostic by just dropping it
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(the|a|an) ", "", s)
    s = re.sub(r" (the|a|an)$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def build_index(tree, folder):
    idx = defaultdict(list)
    for t in tree["tree"]:
        p = t["path"]
        if t["type"] == "blob" and p.startswith(folder + "/") and p.endswith(".png"):
            name = p[len(folder) + 1 : -4]
            idx[norm(name)].append(name)
    return idx


def main():
    tree = json.load(open(TREE, encoding="utf-8"))
    rows = json.load(open(DATA, encoding="utf-8"))
    arc = [r for r in rows if r.get("base") == "Arcade" and not r.get("deprecated")]

    folders = ["Named_Titles", "Named_Snaps", "Named_Boxarts"]
    idx = {f: build_index(tree, f) for f in folders}

    stats = {f: 0 for f in folders}
    any_hit = 0
    misses = []
    for r in arc:
        key = norm(r["title"])
        hits = {f: key in idx[f] for f in folders}
        for f in folders:
            if hits[f]:
                stats[f] += 1
        if any(hits.values()):
            any_hit += 1
        else:
            misses.append(r["title"])

    n = len(arc)
    print(f"arcade titles (non-deprecated): {n}\n")
    for f in folders:
        print(f"  {f:14s}: {stats[f]:4d}  ({100*stats[f]/n:5.1f}%)")
    print(f"  {'ANY image':14s}: {any_hit:4d}  ({100*any_hit/n:5.1f}%)\n")
    print(f"misses: {len(misses)}")
    for m in misses[:40]:
        print("   -", m, " -> norm:", repr(norm(m)))


if __name__ == "__main__":
    main()
