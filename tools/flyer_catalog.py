"""Apply the verified hosted flyer index after every catalogue export."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'data' / 'flyers.json'


def apply_flyers(rows, index):
    assets = index.get('assets', {})
    counts = {'exact': 0, 'family': 0, 'missing': 0}
    for row in rows:
        row.pop('media_key', None)
        row.pop('media_slots', None)
        if row.get('base') != 'Arcade':
            continue
        key = None
        for field, match in [('sn', 'exact'), ('family', 'family')]:
            candidate = row.get(field)
            if candidate and candidate in assets:
                key = candidate
                counts[match] += 1
                break
        if key:
            row.update(media_key=key, media_slots=['flyer'])
        else:
            counts['missing'] += 1
    return counts


def retag():
    if not INDEX.exists():
        return
    path = ROOT / 'docs/releases/data.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    counts = apply_flyers(rows, json.loads(INDEX.read_text(encoding='utf-8')))
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('Flyer coverage:', counts)


if __name__ == '__main__':
    retag()
