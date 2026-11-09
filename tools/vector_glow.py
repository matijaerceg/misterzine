"""Bright, thick, sharp strokes for the screenshots of vector-monitor games.

MAME draws a vector game as hairline strokes on black, which read thin and dim
next to raster games (owner, 2026-11-09: "not broken, just not as nice"). This
brightens the strokes and thickens them with crisp edges, at twice the
capture's resolution, the way they read on an XY monitor. Local tool: it needs
Pillow, and CI never runs it.

Usage: python tools/vector_glow.py           treat every untreated shot
       python tools/vector_glow.py --check   only list what would be treated

A treated PNG carries a text chunk (mz-treatment=vector-glow-2), so a rerun
leaves it alone, while a shot re-extracted from the packs (fetch_images.py
overwrites it with the raw capture) gets treated again; fetch_images.py calls
apply() after its fetch modes for that reason. A shot CI's backfill fetches
for a new vector game stays raw until this runs locally.

Only manifest entries sourced from progettoSNAPS or Arcade Database are
touched. A hand-supplied shot (source "manual", such as Aztarac's two) is left
exactly as given. For a new vector game, add its MAME setname to
VECTOR_SETNAMES and run this.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data/cache/image_manifest.json")
IMGROOT = os.path.join(ROOT, "docs/images")
MARK_KEY, MARK = "mz-treatment", "vector-glow-2"

# MAME sets with a vector display (<display type="vector">) among the games the
# site lists; the repo's caches carry no display type, so this is by hand.
VECTOR_SETNAMES = frozenset("""
    armora asteroid astdelux aztarac barrier bradley bwidow bzone elim2a esb
    gravitar llander mhavoc redbarona ripoff spacewar spacfury starcas starhawk
    startrek starwars tacscan tempest warrior wotw zektor
""".split())
SLOTS = (("title_img", "title"), ("snap_img", "snap"), ("third_img", "ingame"))


def glow(im):
    """The treatment itself; returns an RGB image at TWICE the capture's size
    (MAME's 640x480 vector raster becomes 1280x960). Tuned on that raster."""
    from PIL import Image, ImageChops, ImageFilter

    def gain(src, k):
        return src.point(lambda v: min(255, int(v * k)))

    im = im.convert("RGB")
    # A pure blue or red stroke is dim on its own; phosphor bloom carries a
    # little of every channel, so lift all three by a share of the brightest.
    r, g, b = im.split()
    lift = gain(ImageChops.lighter(ImageChops.lighter(r, g), b), 0.22)
    core = gain(Image.merge("RGB", [ImageChops.add(c, lift) for c in (r, g, b)]), 1.35)
    # Double the resolution first, so the thickened stroke has smooth edges
    # instead of the stair steps a 640-wide file shows when it is enlarged
    # (resampling a one-pixel stroke costs peak brightness, hence the gain).
    big = gain(core.resize((im.width * 2, im.height * 2), Image.BICUBIC), 1.15)
    # a one-pixel stroke becomes about two capture pixels wide, edges just
    # softened enough to hide the steps
    thick = big.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    # A tight, faint rim only. With none, a saturated stroke lights a single
    # stripe of the site's shadow mask and reads dotted in the panel; a wide
    # soft halo (the first version) read as blur (owner, 2026-11-09: "less
    # blurry, just thickened").
    rim = gain(thick.filter(ImageFilter.GaussianBlur(2.5)), 0.45)
    return ImageChops.screen(thick, rim)


def targets(manifest):
    """Paths of the vector games' shots that came from an upstream capture."""
    paths = set()
    for e in manifest:
        sn = (e.get("setname") or "").lower()
        if sn not in VECTOR_SETNAMES or e.get("source") not in ("psnaps", "adb"):
            continue
        for field, slot in SLOTS:
            if e.get(field):
                paths.add(os.path.join(IMGROOT, slot, sn + ".png"))
    return sorted(paths)


def bare_strokes(im):
    """True for hairlines on black, the only thing the treatment suits. A raw
    vector capture lights under 5% of its pixels; one shot with the cabinet's
    painted backdrop behind the strokes (the Asteroids Deluxe title, 31%) is
    already a full picture and the treatment would blow it out. This is no
    guard against treating a file twice: only the text chunk is, so never
    strip PNG metadata from these files."""
    lum = im.convert("L")
    lit = sum(lum.histogram()[41:])
    return lit / (lum.size[0] * lum.size[1]) < 0.15


def apply(check=False):
    """Treat every untreated target. Returns (treated, skipped): the paths
    treated (with check, the ones that would be) and the untreated ones left
    alone because they are not bare strokes."""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    done, skipped = [], []
    for path in targets(manifest):
        if not os.path.exists(path):
            continue
        with Image.open(path) as im:
            if im.info.get(MARK_KEY) == MARK:
                continue
            if not bare_strokes(im):
                skipped.append(path)
                continue
            out = None if check else glow(im)
        done.append(path)
        if out is not None:
            info = PngInfo()
            info.add_text(MARK_KEY, MARK)
            out.save(path, pnginfo=info, optimize=True)
    return done, skipped


def main():
    check = "--check" in sys.argv[1:]
    done, skipped = apply(check=check)
    for path in done:
        print(("would treat " if check else "treated ") + os.path.relpath(path, ROOT))
    for path in skipped:
        print("left alone (not bare strokes) " + os.path.relpath(path, ROOT))
    print(f"{len(done)} vector shots {'need the' if check else 'given the'} glow treatment")


if __name__ == "__main__":
    main()
