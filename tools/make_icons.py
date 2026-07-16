"""Regenerate the PWA / home-screen icons from the wordmark SVG.

Inputs:  logo_white.svg at the repo root -- the MiSTer Zine sticker as a single
         white path. The letter interiors are transparent HOLES in that path,
         so whatever ground the sticker sits on shows through them; the dark
         ground here gives the og-card look.
Outputs: docs/icon-512.png, docs/icon-192.png   (manifest icons, purpose any)
         docs/icon-512-maskable.png             (Android adaptive; safe zone)
         docs/apple-touch-icon.png              (180px, the iOS app icon)

All icons are full-bleed dark squares with no baked-in corner rounding --
iOS and Android apply their own masks, and pre-rounding double-rounds.

Run from anywhere: python tools/make_icons.py
Needs Playwright (chromium) to rasterize the SVG and Pillow to composite.
"""

import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "logo_white.svg"
DOCS = ROOT / "docs"

GROUND = (0x13, 0x13, 0x13)  # theme.css dark --bg; also the manifest colors
MASTER = 1024                # composite at 1024 and downscale for quality
RASTER = 1600                # SVG raster size; ink is trimmed to its bbox after


def rasterize_svg() -> Image.Image:
    """Render the SVG on a transparent ground and trim to the ink's bbox
    (the sticker doesn't fill its viewBox, so the raw screenshot has margins)."""
    html = ("<!doctype html><style>body{margin:0}svg{display:block;"
            f"width:{RASTER}px;height:{RASTER}px}}</style>" + SVG.read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": RASTER, "height": RASTER})
        page.set_content(html)
        shot = page.screenshot(omit_background=True)
        browser.close()
    img = Image.open(io.BytesIO(shot)).convert("RGBA")
    return img.crop(img.getbbox())


def compose(mark: Image.Image, size: int, box_frac: float) -> Image.Image:
    """Center the wordmark on a full-bleed dark square, scaled to fit a
    box_frac-sized square box (whichever of width/height binds)."""
    icon = Image.new("RGBA", (size, size), GROUND + (255,))
    box = size * box_frac
    scale = min(box / mark.width, box / mark.height)
    w, h = round(mark.width * scale), round(mark.height * scale)
    scaled = mark.resize((w, h), Image.LANCZOS)
    icon.alpha_composite(scaled, ((size - w) // 2, (size - h) // 2))
    return icon


def main():
    mark = rasterize_svg()

    # purpose "any": wordmark at 78% of the square
    master = compose(mark, MASTER, 0.78)
    for size, name in ((512, "icon-512.png"), (192, "icon-192.png"),
                       (180, "apple-touch-icon.png")):
        out = master.resize((size, size), Image.LANCZOS).convert("RGB")
        out.save(DOCS / name, optimize=True)
        print(f"wrote docs/{name}")

    # purpose "maskable": Android crops to a shape inside the center 80%
    # circle, so the whole wordmark's half-diagonal must fit that radius
    # (with a small margin) or corners of the mark get clipped on round masks
    r = MASTER * 0.80 / 2 * 0.95
    half_diag = (mark.width ** 2 + mark.height ** 2) ** 0.5 / 2
    # scale s puts the half-diagonal at r; compose() scales the longest side
    # to MASTER*frac, so express s as that frac
    frac = min(r * max(mark.width, mark.height) / (half_diag * MASTER), 0.78)
    maskable = compose(mark, MASTER, frac)
    out = maskable.resize((512, 512), Image.LANCZOS).convert("RGB")
    out.save(DOCS / "icon-512-maskable.png", optimize=True)
    print("wrote docs/icon-512-maskable.png")


if __name__ == "__main__":
    main()
