"""Title -> libretro-thumbnails filename matching for MiSTer arcade titles.

Shared matching logic: normalization (with camelCase split + alias handling)
and canonical candidate selection (region-aware, avoids bootleg/hack/proto).
"""
import json, re
from collections import defaultdict

TREE = "data/cache/libretro_mame_tree.json"
DATA = "docs/releases/data.json"
FOLDERS = ["Named_Titles", "Named_Snaps"]

PAREN = re.compile(r"\([^()]*\)")
CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")

# Sets we never want to pick if anything better exists.
BAD = ("bootleg", "hack", "proto", "prototype", "pirate", "homebrew",
       "demo", "earlier", "bad dump", "program", "no sound")
# Region preference, best first. Matched as whole parenthetical tokens.
REGION_RANK = ["world", "usa", "us", "euro", "europe", "japan", "japan, usa"]


def _strip_parens(s):
    prev = None
    while prev != s:
        prev = s
        s = PAREN.sub(" ", s)
    return s


def norm(s):
    """Normalize a name for fuzzy matching."""
    s = CAMEL.sub(" ", s)            # TankBattalion -> Tank Battalion
    s = s.lower().replace("_", " ")  # libretro encodes &*/:`<>?\| as _
    s = _strip_parens(s)             # drop (Japan), (World, set 1), ...
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^(the|a|an) ", "", s)
    s = re.sub(r" (the|a|an)$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def title_keys(title):
    """Candidate keys for one MiSTer title, best/most-specific first.

    Handles ' - ' alias separators (e.g. 'Galaga 3 - Gaplus' -> both halves,
    'Pac-Man - Puck Man' -> 'pac man' and 'puck man')."""
    keys = [norm(title)]
    if " - " in title:
        for part in title.split(" - "):
            k = norm(part)
            if k and k not in keys:
                keys.append(k)
    return keys


def build_index(tree, folder):
    idx = defaultdict(list)
    for t in tree["tree"]:
        p = t["path"]
        if t["type"] == "blob" and p.startswith(folder + "/") and p.endswith(".png"):
            idx[norm(p[len(folder) + 1 : -4])].append(p[len(folder) + 1 : -4])
    return idx


def _regions(name):
    out = []
    for grp in re.findall(r"\(([^()]*)\)", name.lower()):
        out += [t.strip() for t in grp.split(",")]
    return out


def pick(cands):
    """Pick the most canonical filename from region/set variants."""
    def score(n):
        low = n.lower()
        bad = any(b in low for b in BAD)
        regs = _regions(n)
        rank = min((REGION_RANK.index(r) for r in regs if r in REGION_RANK),
                   default=len(REGION_RANK))
        # 'set 1' beats 'set 2'; fewer parentheticals = more canonical
        setno = next((int(m) for r in regs
                      for m in re.findall(r"set (\d+)", r)), 0)
        nparen = n.count("(")
        return (bad, rank, setno, nparen, len(n), n)
    return sorted(cands, key=score)[0]


def load():
    tree = json.load(open(TREE, encoding="utf-8"))
    rows = json.load(open(DATA, encoding="utf-8"))
    arc = [r for r in rows if r.get("base") == "Arcade" and not r.get("deprecated")]
    idx = {f: build_index(tree, f) for f in FOLDERS}
    return arc, idx


def resolve(title, idx):
    """Return {folder: filename or None} for a title, trying alias keys."""
    out = {}
    for f in FOLDERS:
        hit = None
        for k in title_keys(title):
            if k in idx[f]:
                hit = pick(idx[f][k])
                break
        out[f] = hit
    return out
