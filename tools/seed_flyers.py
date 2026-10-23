"""Normalize a local MAME flyer pack, upload to R2, then publish its verified index.

Usage: python tools/seed_flyers.py PATH --source-url URL --credentials-root PATH
The source directory may contain PNG or JPEG files named by exact MAME setname.
Reruns skip objects whose MD5 already matches; the index is written only after all
objects have been uploaded and their R2 ETags verified.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageOps
import seed_r2

ROOT = Path(__file__).resolve().parents[1]
SAFE = re.compile(r'^[a-z0-9_]{1,32}$')


def normalize(source, destination):
    with Image.open(source) as im:
        im.load()
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((640, 640), Image.Resampling.LANCZOS)
        im.save(destination, format='PNG', optimize=True)
        if destination.stat().st_size > 4 << 20:
            raise ValueError(f'Flyer too large: {source.name}')
        return im.size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('directory', type=Path)
    ap.add_argument('--source-url', required=True)
    ap.add_argument('--credentials-root', type=Path, default=ROOT)
    args = ap.parse_args()
    seed_r2.ROOT = str(args.credentials_root)
    s3 = seed_r2.client()
    stage = ROOT / 'data/cache/flyers'
    stage.mkdir(parents=True, exist_ok=True)
    sources = {}
    rejected = []
    for path in sorted(args.directory.rglob('*')):
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            continue
        if not SAFE.fullmatch(path.stem):
            rejected.append(str(path.relative_to(args.directory)))
            continue
        if path.stem in sources:
            raise ValueError(f'Ambiguous duplicate setname {path.stem}')
        sources[path.stem] = path
    if not sources:
        raise ValueError('No flyers found; refusing empty publication')
    assets = {}
    items = []
    for key, source in sources.items():
        dest = stage / (key + '.png')
        w, h = normalize(source, dest)
        assets[key] = {'width': w, 'height': h, 'bytes': dest.stat().st_size,
                       'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                       'source_file': source.relative_to(args.directory).as_posix()}
        items.append((f'flyer/{key}.png', str(dest)))
    existing = seed_r2.list_keys(s3, 'flyer/')
    print(seed_r2.upload_many(s3, items, args.source_url, 6, False, existing), flush=True)
    verified = seed_r2.list_keys(s3, 'flyer/')
    for key, path in items:
        if verified.get(key) != seed_r2.md5_of(path):
            raise ValueError(f'Upload verification failed: {key}')
    index = {'source_url': args.source_url, 'source_images': len(sources),
             'unmapped_filenames': rejected, 'assets': assets}
    output = ROOT / 'data/flyers.json'
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(index, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(output)
    print(f'Verified {len(assets)} hosted flyers; index written', flush=True)


if __name__ == '__main__':
    main()
