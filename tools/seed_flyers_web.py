"""Publish website JPEG variants from the verified original flyer collection."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps
import seed_r2

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', type=Path)
    parser.add_argument('--thumbnail', action='store_true', help='Prepare 640px sidebar JPEGs')
    parser.add_argument('--credentials-root', type=Path, default=ROOT)
    args = parser.parse_args()
    prefix = 'flyer-thumb' if args.thumbnail else 'flyer-web'
    edge = 640 if args.thumbnail else 1600
    index = json.loads((ROOT / 'data/flyers.json').read_text())
    seed_r2.ROOT = str(args.credentials_root)
    client = seed_r2.client()
    existing = seed_r2.list_keys(client, prefix + '/')
    stage = ROOT / 'data/cache' / prefix
    stage.mkdir(parents=True, exist_ok=True)

    def prepare(item):
        key, meta = item
        source = args.sources / meta['source_file']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == meta['source_sha256'], key
        destination = stage / (key + '.jpg')
        with Image.open(source) as original:
            im = ImageOps.exif_transpose(original).convert('RGB')
            im.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            im.save(destination, 'JPEG', quality=88, optimize=True, progressive=True)
            width, height = im.size
        object_key = prefix + '/' + key + '.jpg'
        digest = seed_r2.md5_of(destination)
        if existing.get(object_key) != digest:
            with destination.open('rb') as stream:
                client.put_object(Bucket=seed_r2.BUCKET, Key=object_key, Body=stream,
                                  ContentType='image/jpeg', Metadata={'w': str(width), 'h': str(height),
                                  'src': index['source_url']})
        return key, {'width': width, 'height': height, 'bytes': destination.stat().st_size,
                     'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                     'source_sha256': meta['source_sha256'], 'etag': digest}

    assets = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for key, metadata in pool.map(prepare, index['assets'].items()):
            assets[key] = metadata
            if len(assets) % 100 == 0:
                print('Prepared/uploaded', len(assets), flush=True)
    verified = seed_r2.list_keys(client, prefix + '/')
    for key, meta in assets.items():
        assert verified.get(prefix + '/' + key + '.jpg') == meta.pop('etag'), key
    result = {'source_url': index['source_url'], 'max_edge': edge, 'jpeg_quality': 88,
              'progressive': True, 'assets': assets}
    temp = ROOT / ('data/' + prefix + '.tmp')
    temp.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    temp.replace(ROOT / ('data/' + ('flyers-thumb' if args.thumbnail else 'flyers-web') + '.json'))
    print('Verified', len(assets), 'JPEGs;', sum(v['bytes'] for v in assets.values()), 'bytes', flush=True)


if __name__ == '__main__':
    main()
