# Flyer collection

MisterZine hosts reduced-size scans of original arcade advertising flyers for
game identification and historical reference. The artwork remains the property
of its original publishers and other rights holders.

The source is `flyers/flyers.zip` in the public
[MAME 0.279 EXTRAs archive](https://archive.org/details/mame_extras-0.279).
The ZIP member is dated March 31, 2023; this is a mirrored collection, not a
claim to the newest available flyer scans. It contains 5,123 named PNG images
and no accompanying README or licence. Hosting does not confer a new licence
to the underlying artwork.

We selected every image whose exact MAME setname appears as a catalogue row's
setname or declared family: 1,195 images. The other 3,928 archive images belong
to sets outside that selection and are not mirrored here. Titles and screenshot
filenames are not used as approximate matches. Each retrieved image was checked
against the ZIP's original size and CRC32 before conversion.

Hosted PNGs fit within 640 by 640 pixels, retain aspect ratio and contain no
added branding. The machine-readable `data/flyers.json` in the source repository
records original filenames, source and hosted SHA256 hashes, hosted dimensions,
and source URL. An exact setname takes precedence over family artwork.

The initial import covers 1,374 of 2,424 arcade catalogue rows: 1,314 exact
setname matches and 60 family fallbacks. Rows include regional versions and
different core implementations, so this is not a count of distinct games.
The remaining 1,050 rows have no matching flyer in this collection.

Flyers appear in website detail galleries and on supported device builds;
website list cards retain screenshots. Games without a matching flyer omit it.

Website lightboxes use separate progressive JPEGs, quality 88, up to 1600 pixels on the longest edge. Smaller originals are not enlarged during conversion. These are generated from the original scans, not the device PNGs. Their dimensions and hashes are recorded in `data/flyers-web.json`; `tools/seed_flyers_web.py` prepares and verifies uploads. Device PNGs remain unchanged.

Sidebar images use separate 640px JPEGs at `/flyer-thumb/<setname>.jpg`, prepared with the same tool using `--thumbnail`. The 1600px image is loaded only on opening the lightbox.
