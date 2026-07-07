"""Dry-run image manifest: resolve title + snap + one in-game shot per arcade
title, deterministically by MAME setname against progettoSNAPS packs, using the
MAME DAT's cloneof to fall back to the parent set. Falls back to libretro
display-name matching for titles that have no setname.

Downloads nothing except metadata (cached). Writes data/cache/image_manifest.json.
"""
import json, re, os, sqlite3
import match  # libretro fallback
import setname_backfill
from probe_psnaps2 import pack_setnames, BASE, PACKS

DAT = "data/cache/MAME_arcade.dat"
PACKS_CACHE = "data/cache/psnaps_packs.json"
OUT = "data/cache/image_manifest.json"
# MiSTer .mra setnames that predate a MAME rename, so they match nothing in the
# current progettoSNAPS packs. Pin each to the live MAME set (parent preferred,
# so all three image slots — which the site keys off one setname — self-match).
SETNAME_ALIASES = {
    # "Pop Flamer (Bootleg conversion)" ships as `popflamn`; MAME renamed it to
    # `popflamen` (clone of parent `popflame`). Only the parent carries a
    # gameover shot, so alias to the parent for a consistent full trio.
    "popflamn": "popflame",
}
# Order of preference for the third (in-game) shot.
THIRD = ["gameover", "scores", "select", "bosses", "versus", "howto"]
MACHINE = re.compile(r'<machine\s+name="([^"]+)"[^>]*?(?:\scloneof="([^"]+)")?[^>]*>')


def load_cloneof():
    """setname -> parent setname (or itself) from the MAME arcade DAT."""
    text = open(DAT, encoding="utf-8", errors="ignore").read()
    parent = {}
    for m in MACHINE.finditer(text):
        parent[m.group(1)] = m.group(2) or m.group(1)
    return parent


def load_packs():
    if os.path.exists(PACKS_CACHE):
        return {k: set(v) for k, v in json.load(open(PACKS_CACHE)).items()}
    packs = {k: sorted(pack_setnames(BASE + fn)) for k, fn in PACKS.items()}
    json.dump(packs, open(PACKS_CACHE, "w"))
    return {k: set(v) for k, v in packs.items()}


def in_pack(setname, parent, pack):
    """Return the setname that resolves in this pack (self, else parent)."""
    if setname in pack:
        return setname
    if parent in pack:
        return parent
    return None


def main():
    parent_of = load_cloneof()
    packs = load_packs()
    desc_idx = setname_backfill.load_desc_index()  # MAME description -> setname
    con = sqlite3.connect("data/misterzine.sqlite"); con.row_factory = sqlite3.Row
    # Catalog setnames key off raw titles; site data.json titles are cleaned.
    # Join on normalized title so the setname actually reaches each site row.
    setmap = {}
    for r in con.execute("SELECT title,setname FROM catalog "
                         "WHERE system='arcade' AND setname IS NOT NULL"):
        setmap.setdefault(match.norm(r["title"]), r["setname"].lower())

    arc, lidx = match.load()  # arc rows + libretro index for fallback
    manifest = []
    n_title = n_snap = n_third = n_trio = n_libfallback = 0
    for r in arc:
        title = r["title"]
        sn = setmap.get(match.norm(title))
        if not sn:  # backfill from MAME descriptions for setname-less titles
            sn = setname_backfill.resolve_setname(title, desc_idx, prefer=packs["snap"])
        sn = SETNAME_ALIASES.get(sn, sn)  # pin renamed MiSTer setnames to MAME
        entry = {"title": title, "setname": sn, "source": None,
                 "title_img": None, "snap_img": None, "third_img": None, "third_pack": None}
        if sn:
            par = parent_of.get(sn, sn)
            entry["source"] = "psnaps"
            t = in_pack(sn, par, packs["titles"])
            s = in_pack(sn, par, packs["snap"])
            entry["title_img"] = t and f"titles/{t}.png"
            entry["snap_img"] = s and f"snap/{s}.png"
            for p in THIRD:
                hit = in_pack(sn, par, packs[p])
                if hit:
                    entry["third_img"] = f"{p}/{hit}.png"
                    entry["third_pack"] = p
                    break
        else:
            # libretro display-name fallback (title + snap only)
            res = match.resolve(title, lidx)
            if res["Named_Titles"] or res["Named_Snaps"]:
                entry["source"] = "libretro"
                entry["title_img"] = res["Named_Titles"] and f"Named_Titles/{res['Named_Titles']}.png"
                entry["snap_img"] = res["Named_Snaps"] and f"Named_Snaps/{res['Named_Snaps']}.png"
                n_libfallback += 1

        if entry["title_img"]:
            n_title += 1
        if entry["snap_img"]:
            n_snap += 1
        if entry["third_img"]:
            n_third += 1
        if entry["title_img"] and entry["snap_img"] and entry["third_img"]:
            n_trio += 1
        manifest.append(entry)

    json.dump(manifest, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n = len(arc)
    pct = lambda x: f"{x:4d} ({100*x/n:4.1f}%)"
    print(f"arcade titles: {n}\n")
    print(f"  with a title screen : {pct(n_title)}")
    print(f"  with a gameplay snap: {pct(n_snap)}")
    print(f"  with a 3rd (in-game): {pct(n_third)}")
    print(f"  FULL TRIO           : {pct(n_trio)}")
    print(f"  (via libretro fallbk: {n_libfallback})\n")
    miss = [e["title"] for e in manifest if not e["title_img"] and not e["snap_img"]]
    print(f"  no image at all     : {pct(len(miss))}")
    for t in miss[:30]:
        print("     -", t)


if __name__ == "__main__":
    main()
