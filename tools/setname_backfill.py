"""Resolve a setname for titles that lack one, by matching against MAME DAT
descriptions (parent-preferred). Shared by the manifest builder."""
import re, html
import match

DAT = "data/cache/MAME_arcade.dat"
# capture each machine's name, optional cloneof, and description
MACHINE = re.compile(
    r'<machine\s+name="([^"]+)"([^>]*)>\s*<description>([^<]*)</description>', re.S)


def load_desc_index():
    """norm(description) -> list of (setname, is_clone) candidates."""
    text = open(DAT, encoding="utf-8", errors="ignore").read()
    idx = {}
    for m in MACHINE.finditer(text):
        name, attrs, desc = m.group(1), m.group(2), html.unescape(m.group(3))
        is_clone = "cloneof=" in attrs
        for key in match.title_keys(desc):
            idx.setdefault(key, []).append((name, is_clone))
    return idx


# Non-arcade machine families whose setnames collide with real arcade titles:
# fruit machines (m1*/m4*/m5*/j2*/j6*...), Mega-Tech (mt_), PlayChoice (pc_),
# Nintendo Super System (nss_), SkillsPin/Scorpion (sp_), etc. They use an
# underscore family prefix or a single-letter+digit prefix.
COLLECTION = re.compile(r"^[a-z]\d|_")


def looks_collection(name):
    return bool(COLLECTION.search(name))


def resolve_setname(title, desc_idx, prefer=None):
    """Pick a setname for a title. Among same-description candidates, prefer a
    bare arcade-style setname over collection families (fruit/Mega-Tech/etc.),
    then parents over clones, then membership in `prefer` (pS snap inventory)."""
    prefer = prefer or set()
    for key in match.title_keys(title):
        cands = desc_idx.get(key)
        if not cands:
            continue
        best = sorted(cands, key=lambda c: (
            looks_collection(c[0]), c[1], c[0] not in prefer, c[0]))
        return best[0][0]
    return None


if __name__ == "__main__":
    import json
    m = json.load(open("data/cache/image_manifest.json", encoding="utf-8"))
    titles = [e["title"] for e in m if e["source"] != "psnaps"]
    idx = load_desc_index()
    snap = set(json.load(open("data/cache/psnaps_packs.json")).get("snap", []))
    hit = 0
    for t in titles:
        sn = resolve_setname(t, idx, prefer=snap)
        hit += bool(sn)
        print(f"  {('OK '+sn) if sn else 'MISS':16s} | {t}")
    print(f"\nresolved {hit}/{len(titles)}")
