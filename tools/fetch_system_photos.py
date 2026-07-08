"""Fetch console/computer hardware photos from Wikimedia Commons for the
detail-panel system images (docs/images/systems/<core>.png).

For each non-arcade core: try the curated CANDIDATES filenames first, then a
Commons full-text search (namespace 6). Downloads a ~240px server-side thumb
via Special:FilePath. Images with a real alpha channel are quantized to the
fixed DawnBringer-16 palette with Floyd-Steinberg dithering (the deliberate
lo-fi look — see memory: the color casts are the point) and published;
opaque photos (background present) are saved to data/cache/system_photos/todo/
for a manual background-removal pass, and pristine originals of published
images to data/cache/system_photos/orig/.

License/artist metadata for every chosen file is written to
docs/images/systems/credits.json (Commons files are PD or CC — CC-BY-SA ones
need user-visible attribution before going live).

Needs: Pillow (pip install pillow). Re-runnable: existing published PNGs are
kept (delete one to re-fetch it). Rate-limited ~2.5s/request to stay under
Commons throttling (429s otherwise).
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

import certifi
from PIL import Image

# Windows Python's default cert chain is stale (expired-cert failures against
# Wikimedia) — verify against certifi's bundle instead. Keep certifi upgraded.
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# Windows console is cp1252; Commons filenames can be CJK/Cyrillic
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, 'docs', 'images', 'systems')
ORIG = os.path.join(ROOT, 'data', 'cache', 'system_photos', 'orig')
TODO = os.path.join(ROOT, 'data', 'cache', 'system_photos', 'todo')
CREDITS = os.path.join(PUB, 'credits.json')

UA = 'misterzine-system-photos/1.0 (https://github.com/matijaerceg/misterzine; matija.erceg@gmail.com)'
WIDTH = 240
SLEEP = 2.5

# DawnBringer 16 — the chosen fixed lo-fi palette (do NOT change casually;
# the user picked this look over higher-fidelity options on purpose)
DB16 = [(20, 12, 28), (68, 36, 52), (48, 52, 109), (78, 74, 78),
        (133, 76, 48), (52, 101, 36), (208, 70, 72), (117, 113, 97),
        (89, 125, 206), (210, 125, 44), (133, 149, 161), (109, 170, 44),
        (210, 170, 153), (109, 194, 202), (218, 212, 94), (222, 238, 214)]

# Cores that are software/homebrew/no meaningful hardware — no photo by design
SKIP = {'Chess', 'Chip8', 'Donut', 'FlappyBird', 'GameOfLife', 'SlugCross',
        'computerspace', 'pacman', 'MultiComp', 'GBMidi', 'GenMidi'}

# core -> core whose published image is copied (hardware is the same)
ALIASES = {
    'Gameboy2P': 'Gameboy',
    'GBA2P': 'GBA',
    'GnW': 'GameAndWatch',
    'MSX1': 'MSX',
}

# Curated Commons filename guesses, tried in order (mostly Evan-Amos /
# Vanamo Online Game Museum transparent sets — public domain)
CANDIDATES = {
    'NES': ['NES-Console-Set.png'],
    'SNES': ['SNES-Mod1-Console-Set.png'],
    'Genesis': ['Sega-Genesis-Mod1-Set.png'],
    'MegaDrive': ['Sega-Mega-Drive-JP-Mk1-Console-Set.png', 'Sega-Genesis-Mod1-Set.png'],
    'Gameboy': ['Game-Boy-FL.png'],
    'GBA': ['Nintendo-Game-Boy-Advance-Purple-FL.png', 'Game-Boy-Advance-1stGen.png'],
    'N64': ['N64-Console-Set.png', 'Nintendo-64-wController-L.png'],
    'Vectrex': ['Vectrex-Console-Set.png'],
    'C64': ['Commodore-64-Computer-FL.png'],
    'C128': ['Commodore-128-Computer-FL.png'],
    'VIC20': ['Commodore-VIC-20-FL.png'],
    'PET2001': ['Commodore-PET-2001-FL.png', 'Commodore 2001 Series-IMG 0448b.jpg'],
    'PSX': ['PSX-Console-wController.png', 'PlayStation-SCPH-1000-with-Controller.png'],
    'Saturn': ['Sega-Saturn-JP-Mk1-Console-Set.png', 'Sega-Saturn-Console-Set-Mk1.png'],
    'SMS': ['Sega-Master-System-Set.png', 'Master-System-Set.png'],
    'GameGear2P': ['Sega-Game-Gear-WB.png', 'Game-Gear-Handheld.png'],
    'MegaCD': ['Sega-CD-Model1-Set.png'],
    'S32X': ['Sega-Genesis-Model2-with-32X.png', 'Sega-32X-Add-on.png'],
    'TurboGrafx16': ['TurboGrafx-16-Console-Set.png', 'TurboGrafx16-Console-Set.png'],
    'NeoGeo': ['Neo-Geo-AES-Console-Set.png', 'Neo-Geo-AES.png'],
    'NeoGeoPocket': ['Neo-Geo-Pocket-Color-FL.png', 'Neo-Geo-Pocket-Handheld.png'],
    'WonderSwan': ['WonderSwan-Color-Blue-Left.png', 'Bandai-WonderSwan-Color-Blue.png'],
    'Jaguar': ['Atari-Jaguar-Console-Set.png'],
    'AtariLynx': ['Atari-Lynx-I-Handheld.png', 'Atari-Lynx-Handheld.png'],
    'Atari5200': ['Atari-5200-4-Port-wController-L.png', 'Atari-5200-Console-Set.png'],
    'Atari7800': ['Atari-7800-Console-Set.png'],
    'Atari800': ['Atari-800-Computer-FL.png'],
    'Intellivision': ['Intellivision-Console-Set.png'],
    'ColecoVision': ['ColecoVision-wController-L.png', 'ColecoVision-Console-Set.png'],
    'Odyssey2': ['Magnavox-Odyssey-2-Console-Set.png', 'Magnavox-Odyssey-II.png'],
    'ChannelF': ['Fairchild-Channel-F.png', 'Fairchild-Channel-F-Console.png'],
    'Astrocade': ['Bally-Professional-Arcade-Console.png', 'Bally-Astrocade.png'],
    'CDi': ['CD-i-910-Console-Set.png', 'Philips-CD-i-910.png'],
    'ColecoAdam': ['Coleco-Adam-Computer.png'],
    'Aquarius': ['Mattel-Aquarius-Computer-FL.png', 'Mattel-Aquarius.png'],
    'Arcadia': ['Emerson-Arcadia-2001.png'],
    'AdventureVision': ['Entex-Adventure-Vision.png'],
    'SuperVision': ['Watara-Supervision.png', 'Watara-Supervision-Handheld.png'],
    'PokemonMini': ['Pokemon-Mini-Handheld.png', 'Pokemon-Mini.png'],
    'GameAndWatch': ['Game-&-Watch-Ball.png', 'Nintendo-Game-&-Watch-Ball.png'],
    'SGB': ['SNES-Super-Game-Boy.png', 'Super-Game-Boy.png'],
    'ZX81': ['Sinclair-ZX81.png'],
    'Ti994a': ['TI-99-4A-Computer-FL.png', 'TI-99-4A Computer.png'],
    'Gamate': ['Gamate-Handheld.png', 'Bit-Corporation-Gamate.png'],
    'CreatiVision': ['VTech-CreatiVision.png'],
    'VC4000': ['Interton-VC-4000.png'],
    'SCV': ['Epoch-Super-Cassette-Vision.png'],
}

# Commons full-text search fallback (namespace 6 = File:)
SEARCH = {
    'AcornAtom': 'Acorn Atom computer',
    'AcornElectron': 'Acorn Electron computer',
    'AdventureVision': 'Entex Adventure Vision',
    'AliceMC10': 'Matra Alice computer',
    'Altair8800': 'Altair 8800 computer',
    'Amstrad': 'Amstrad CPC 464',
    'Amstrad-PCW': 'Amstrad PCW computer',
    'ao486': 'Intel i486 DX2 processor',
    'Apogee': 'Apogey BK-01 computer',
    'Apple-I': 'Apple I computer',
    'Apple-II': 'Apple II computer 1977',
    'Aquarius': 'Mattel Aquarius computer',
    'Arcadia': 'Emerson Arcadia 2001',
    'Archie': 'Acorn Archimedes computer',
    'Arduboy': 'Arduboy handheld',
    'Astrocade': 'Bally Astrocade console',
    'Atari5200': 'Atari 5200 console',
    'Atari7800': 'Atari 7800 console',
    'Atari800': 'Atari 800 computer',
    'AtariLynx': 'Atari Lynx handheld',
    'AtariST': 'Atari 1040ST computer',
    'AY-3-8500': 'AY-3-8500 chip',
    'BBCBridgeCompanion': 'BBC Bridge Companion',
    'BBCMicro': 'BBC Micro computer',
    'BK0011M': 'Elektronika BK-0010 computer',
    'C128': 'Commodore 128 computer',
    'C16': 'Commodore 16 computer',
    'Casio_PV-1000': 'Casio PV-1000 console',
    'Casio_PV-2000': 'Casio PV-2000 computer',
    'CDi': 'Philips CD-i 910 console',
    'ChannelF': 'Fairchild Channel F console',
    'CoCo2': 'TRS-80 Color Computer 2',
    'CoCo3': 'TRS-80 Color Computer 3',
    'ColecoAdam': 'Coleco Adam computer',
    'ColecoVision': 'ColecoVision console',
    'CreatiVision': 'VTech CreatiVision console',
    'EDSAC': 'EDSAC computer',
    'eg2000': 'EACA Colour Genie EG2000',
    'Enterprise': 'Enterprise 128 computer',
    'EpochGalaxyII': 'Epoch Galaxy II game',
    'Galaksija': 'Galaksija computer',
    'Gamate': 'Gamate handheld console',
    'GameAndWatch': 'Nintendo Game and Watch Ball',
    'GameGear2P': 'Sega Game Gear handheld',
    'GBA': 'Game Boy Advance handheld',
    'Homelab': 'Homelab computer Hungarian',
    'Intellivision': 'Intellivision console',
    'Interact': 'Interact Home Computer',
    'IQ151': 'IQ 151 computer',
    'Jaguar': 'Atari Jaguar console',
    'Jupiter': 'Jupiter Ace computer',
    'Laser310': 'VTech Laser 310 computer',
    'Lynx48': 'Camputers Lynx computer',
    'MacPlus': 'Macintosh Plus computer',
    'MegaCD': 'Sega CD console',
    'MegaDrive': 'Sega Mega Drive console',
    'MSX': 'MSX computer Sony HitBit',
    'MyVision': 'Nichibutsu My Vision',
    'N64': 'Nintendo 64 console',
    'NeoGeo': 'Neo Geo AES console',
    'NeoGeoPocket': 'Neo Geo Pocket Color',
    'Odyssey2': 'Magnavox Odyssey 2 console',
    'Ondra_SPO186': 'Ondra SPO 186 computer',
    'ORAO': 'Orao computer',
    'Oric': 'Oric-1 computer',
    'PC88': 'NEC PC-8801 computer',
    'PCjr': 'IBM PCjr computer',
    'PCXT': 'IBM PC XT computer',
    'PDP1': 'DEC PDP-1 computer',
    'PET2001': 'Commodore PET 2001 computer',
    'PMD85': 'PMD 85 computer',
    'PokemonMini': 'Pokemon Mini handheld',
    'PSX': 'Sony PlayStation console',
    'QL': 'Sinclair QL computer',
    'RX78': 'Bandai RX-78 computer',
    'S32X': 'Sega 32X',
    'SAMCoupe': 'SAM Coupe computer',
    'Saturn': 'Sega Saturn console',
    'SCV': 'Epoch Super Cassette Vision',
    'SGB': 'Super Game Boy',
    'SharpMZ': 'Sharp MZ-80K computer',
    'SMS': 'Sega Master System console',
    'SordM5': 'Sord M5 computer',
    'Specialist': 'Specialist computer Soviet',
    'Super_Vision_8000': 'Bandai Super Vision 8000',
    'SuperVision': 'Watara Supervision handheld',
    'Svi328': 'Spectravideo SVI-328',
    'Tamagotchi': 'Tamagotchi original 1996',
    'Tandy1000': 'Tandy 1000 computer',
    'TatungEinstein': 'Tatung Einstein computer',
    'Ti994a': 'Texas Instruments TI-99/4A',
    'TK2000': 'Microdigital TK2000 computer',
    'TomyScramble': 'Tomy Scramble tabletop game',
    'TomyTutor': 'Tomy Tutor computer',
    'TRS-80': 'TRS-80 Model I computer',
    'TSConf': 'ZX Evolution computer',
    'TurboGrafx16': 'TurboGrafx-16 console',
    'UK101': 'Compukit UK101 computer',
    'VC4000': 'Interton VC 4000 console',
    'Vector-06C': 'Vector-06C computer',
    'VT52': 'DEC VT52 terminal',
    'WonderSwan': 'WonderSwan handheld',
    'X68000': 'Sharp X68000 computer',
    'ZXNext': 'ZX Spectrum Next',
    'ZX-Spectrum': 'ZX Spectrum 48k computer',
}

BAD_TITLE_WORDS = ('logo', 'screenshot', 'schematic', 'diagram', 'icon',
                   'motherboard', 'pcb', 'font', 'ad ', 'advertisement')
BAD_EXT = ('.svg', '.pdf', '.djvu', '.ogv', '.webm', '.gif', '.stl')


def http_get(url, binary=True):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
        data = r.read()
    return data if binary else json.loads(data.decode('utf-8'))


def fetch_thumb(commons_name):
    """Download a WIDTH-px thumb of a Commons file; None on any failure."""
    url = ('https://commons.wikimedia.org/wiki/Special:FilePath/'
           + urllib.parse.quote(commons_name) + f'?width={WIDTH}')
    time.sleep(SLEEP)
    try:
        data = http_get(url)
    except Exception as e:
        print(f'    miss ({e}): {commons_name}')
        return None
    if not (data[:4] == b'\x89PNG' or data[:2] == b'\xff\xd8'):
        print(f'    not an image: {commons_name}')
        return None
    return data


def search_commons(query):
    """Top File: hits for a query, filtered to plausible photo files."""
    url = ('https://commons.wikimedia.org/w/api.php?action=query&list=search'
           '&srnamespace=6&srlimit=8&format=json&srsearch='
           + urllib.parse.quote(query))
    time.sleep(SLEEP)
    try:
        js = http_get(url, binary=False)
    except Exception as e:
        print(f'    search failed: {e}')
        return []
    out = []
    for hit in js.get('query', {}).get('search', []):
        title = hit['title'][len('File:'):]
        low = title.lower()
        if low.endswith(BAD_EXT) or any(w in low for w in BAD_TITLE_WORDS):
            continue
        out.append(title)
    return out


def file_meta(commons_name):
    """License/artist from Commons extmetadata (for the credits file)."""
    url = ('https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo'
           '&iiprop=extmetadata&format=json&titles='
           + urllib.parse.quote('File:' + commons_name))
    time.sleep(SLEEP)
    try:
        js = http_get(url, binary=False)
        pages = js['query']['pages']
        em = next(iter(pages.values()))['imageinfo'][0]['extmetadata']
        get = lambda k: em.get(k, {}).get('value', '')
        return {'license': get('LicenseShortName'),
                'artist': get('Artist'), 'file': commons_name}
    except Exception:
        return {'license': '?', 'artist': '?', 'file': commons_name}


def has_alpha(im):
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    lo, hi = im.getchannel('A').getextrema()
    return lo < 128  # some genuinely transparent area, not just soft edges


def publish(im, core):
    """Hard 1-bit alpha + DB16 Floyd-Steinberg quantize -> docs/images/systems."""
    im = im.convert('RGBA')
    alpha = im.getchannel('A').point(lambda v: 255 if v > 128 else 0)
    # trim transparent padding (some sources center a small subject in a large
    # canvas, which wastes panel space) — crop to the alpha bbox + 2px margin
    bbox = alpha.getbbox()
    if bbox:
        bbox = (max(0, bbox[0] - 2), max(0, bbox[1] - 2),
                min(im.width, bbox[2] + 2), min(im.height, bbox[3] + 2))
        im, alpha = im.crop(bbox), alpha.crop(bbox)
    pal = Image.new('P', (1, 1))
    pal.putpalette([c for rgb in DB16 for c in rgb] + [0] * (768 - 3 * len(DB16)))
    q = im.convert('RGB').quantize(palette=pal,
                                   dither=Image.Dither.FLOYDSTEINBERG).convert('RGB')
    q.putalpha(alpha)
    q.save(os.path.join(PUB, core + '.png'), optimize=True)


def main():
    for d in (PUB, ORIG, TODO):
        os.makedirs(d, exist_ok=True)
    credits = {}
    if os.path.exists(CREDITS):
        credits = json.load(open(CREDITS, encoding='utf-8'))
    report = {'published': [], 'todo': [], 'miss': [], 'skipped': []}

    cores = sorted(set(list(CANDIDATES) + list(SEARCH)))
    only = sys.argv[1:]
    if only:
        cores = [c for c in cores if c in only]

    for core in cores:
        if core in SKIP or core in ALIASES:
            continue
        if (os.path.exists(os.path.join(PUB, core + '.png'))
                or os.path.exists(os.path.join(TODO, core + '.png'))
                or os.path.exists(os.path.join(TODO, core + '.jpg'))):
            report['skipped'].append(core)
            continue
        print(core)
        names = list(CANDIDATES.get(core, []))
        chosen, data = None, None
        for name in names:
            data = fetch_thumb(name)
            if data:
                chosen = name
                break
        if not chosen and core in SEARCH:
            for name in search_commons(SEARCH[core])[:3]:
                data = fetch_thumb(name)
                if data:
                    chosen = name
                    break
        if not chosen:
            print('    NO IMAGE FOUND')
            report['miss'].append(core)
            continue

        from io import BytesIO
        im = Image.open(BytesIO(data))
        if has_alpha(im):
            with open(os.path.join(ORIG, core + '.png'), 'wb') as f:
                f.write(data)
            publish(im, core)
            credits[core] = file_meta(chosen)
            report['published'].append(core)
            print(f'    published: {chosen}')
        else:
            ext = '.png' if data[:4] == b'\x89PNG' else '.jpg'
            with open(os.path.join(TODO, core + ext), 'wb') as f:
                f.write(data)
            credits[core] = file_meta(chosen)
            credits[core]['todo'] = True
            report['todo'].append(core)
            print(f'    opaque -> todo: {chosen}')

    # aliases: copy the published source file
    for dst, src in ALIASES.items():
        s = os.path.join(PUB, src + '.png')
        d = os.path.join(PUB, dst + '.png')
        if os.path.exists(s) and not os.path.exists(d):
            with open(s, 'rb') as f:
                blob = f.read()
            with open(d, 'wb') as f:
                f.write(blob)
            if src in credits:
                credits[dst] = credits[src]
            report['published'].append(dst + f' (= {src})')

    with open(CREDITS, 'w', encoding='utf-8') as f:
        json.dump(credits, f, indent=1, ensure_ascii=False)
    with open(os.path.join(ROOT, 'data', 'cache', 'system_photos', 'report.json'),
              'w', encoding='utf-8') as f:
        json.dump(report, f, indent=1)
    print('\n=== summary ===')
    for k in ('published', 'todo', 'miss', 'skipped'):
        print(f'{k}: {len(report[k])}')
        if report[k]:
            print('   ' + ', '.join(report[k]))


if __name__ == '__main__':
    main()
