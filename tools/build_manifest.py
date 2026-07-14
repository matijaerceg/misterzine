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
# Hand-pinned libretro filename stems where the canonical pick is a different
# machine: the site's Devil Fish row is the Galaxian-hardware bootleg
# (devilfsg), but the plain "Devil Fish.png" is the Mars-hardware original
# (devilfsh) — different visuals entirely.
LIBRETRO_OVERRIDES = {
    "Devil Fish": "Devil Fish (Galaxian hardware, bootleg_)",
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
    # titles deliberately shown WITHOUT a screenshot (user call): multi-game
    # carts where any single game's shot misrepresents the row
    NO_IMAGE_TITLES = {"CPS1 Multi Game"}
    # titles whose upstream TITLE-screen capture is corrupt across every source
    # (progettoSNAPS/ADB/libretro all ship one identical broken ST-V grab) —
    # drop just that slot and keep the good snap + in-game shots.
    NO_TITLE_TITLES = {"Tecmo World Cup '98"}
    # hand-wired screenshots (source="manual": web-sourced shots for games absent
    # from psnaps/libretro — TTL games, hacks, non-MAME titles). Kept across
    # rebuilds unless the fresh resolution actually finds a real source.
    prev_manual = {}
    if os.path.exists(OUT):
        try:
            prev_manual = {e["title"]: e for e in json.load(open(OUT, encoding="utf-8"))
                           if e.get("source") == "manual"}
        except Exception:
            pass
    manifest = []
    n_title = n_snap = n_third = n_trio = n_libfallback = 0
    for r in arc:
        # key entries by the RAW title (mt): fetch_images and the CI libretro
        # backfill both look manifest entries up by `mt or title`, and since
        # title humanization the display title no longer matches that key
        title = r.get("mt") or r["title"]
        # the row's own setname (stamped at export from the catalog) is the
        # truth. The norm-title join strips parentheticals, so siblings that
        # differ only by a paren qualifier collapse to one key and the first
        # setname wins for both (both Darius II rows got darius2d) — keep it,
        # and the desc-index, as fallbacks for setname-less rows only.
        sn = (r.get("sn") or "").lower() or setmap.get(match.norm(title))
        if not sn:  # backfill from MAME descriptions for setname-less titles
            sn = setname_backfill.resolve_setname(title, desc_idx, prefer=packs["snap"])
        sn = SETNAME_ALIASES.get(sn, sn)  # pin renamed MiSTer setnames to MAME
        entry = {"title": title, "setname": sn, "source": None,
                 "title_img": None, "snap_img": None, "third_img": None, "third_pack": None}
        if sn:
            par = parent_of.get(sn, sn)
            t = in_pack(sn, par, packs["titles"])
            s = in_pack(sn, par, packs["snap"])
            # claim psnaps only when the packs actually have something —
            # otherwise fall through so the libretro fallback and the manual
            # preservation below still get their chance (a setname alone used
            # to stamp source="psnaps" with no images, clobbering both)
            if t or s:
                entry["source"] = "psnaps"
                entry["title_img"] = t and f"titles/{t}.png"
                entry["snap_img"] = s and f"snap/{s}.png"
                for p in THIRD:
                    hit = in_pack(sn, par, packs[p])
                    if hit:
                        entry["third_img"] = f"{p}/{hit}.png"
                        entry["third_pack"] = p
                        break
        if not entry["title_img"] and not entry["snap_img"]:
            # libretro display-name fallback (title + snap only) — for rows
            # with no setname AND for setnames the psnaps packs don't carry
            pin = LIBRETRO_OVERRIDES.get(title)
            res = ({"Named_Titles": pin, "Named_Snaps": pin} if pin
                   else match.resolve(title, lidx))
            if res["Named_Titles"] or res["Named_Snaps"]:
                entry["source"] = "libretro"
                entry["title_img"] = res["Named_Titles"] and f"Named_Titles/{res['Named_Titles']}.png"
                entry["snap_img"] = res["Named_Snaps"] and f"Named_Snaps/{res['Named_Snaps']}.png"
                n_libfallback += 1

        if title in NO_IMAGE_TITLES:
            entry = {"title": title, "setname": entry["setname"], "source": None,
                     "title_img": None, "snap_img": None, "third_img": None, "third_pack": None}
        elif entry["source"] is None and title in prev_manual:
            entry = prev_manual[title]
        if title in NO_TITLE_TITLES:
            entry["title_img"] = None
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
