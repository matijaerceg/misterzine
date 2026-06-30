"""Probe progettoSNAPS coverage by reading each pack's embedded DAT list
(setname inventory) over HTTP Range — no image/7z payload download."""
import urllib.request, struct, zlib, re, sqlite3

BASE = "https://www.progettosnaps.net/snapshots/packs/full_sets/"
PACKS = {
    "snap":     "pS_snap_fullset_287.zip",
    "titles":   "pS_titles_fullset_287.zip",
    "gameover": "pS_gameover_fullset_270.zip",
    "scores":   "pS_scores_fullset_270.zip",
    "select":   "pS_select_fullset_270.zip",
    "versus":   "pS_versus_fullset_270.zip",
    "howto":    "pS_howto_fullset_270.zip",
    "bosses":   "pS_bosses_fullset_270.zip",
}
UA = {"User-Agent": "Mozilla/5.0 misterzine-probe"}


def rng(url, start, end):
    h = dict(UA, Range=f"bytes={start}-{end}")
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90).read()


def head_len(url):
    r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=30)
    return int(r.headers["Content-Length"])


def central_dir(url):
    size = head_len(url)
    buf = rng(url, size - min(size, 1 << 16), size - 1)
    p = buf.rfind(b"PK\x05\x06")
    cd_size, cd_off = struct.unpack("<I", buf[p+12:p+16])[0], struct.unpack("<I", buf[p+16:p+20])[0]
    cd = rng(url, cd_off, cd_off + cd_size - 1)
    out, i = [], 0
    while i + 46 <= len(cd) and cd[i:i+4] == b"PK\x01\x02":
        method, = struct.unpack("<H", cd[i+10:i+12])
        csize, = struct.unpack("<I", cd[i+20:i+24])
        nlen, elen, clen = struct.unpack("<HHH", cd[i+28:i+34])
        lho, = struct.unpack("<I", cd[i+42:i+46])
        name = cd[i+46:i+46+nlen].decode("utf-8", "ignore")
        out.append((name, method, csize, lho))
        i += 46 + nlen + elen + clen
    return out


def read_member(url, entry):
    name, method, csize, lho = entry
    # local header: 30 + nlen + elen, then data
    lh = rng(url, lho, lho + 30 - 1)
    nlen, elen = struct.unpack("<HH", lh[26:30])
    start = lho + 30 + nlen + elen
    raw = rng(url, start, start + csize - 1)
    return zlib.decompress(raw, -15) if method == 8 else raw


def pack_setnames(url):
    cd = central_dir(url)
    dat = next((e for e in cd if e[0].lower().endswith(".dat") and "/" in e[0]), None) \
        or next((e for e in cd if e[0].lower().endswith(".dat")), None)
    if not dat:
        raise RuntimeError("no DAT in " + url)
    text = read_member(url, dat).decode("utf-8", "ignore")
    # Logiqx DAT: each image is <rom name="setname.png" .../>
    return {m[:-4] for m in re.findall(r'<rom name="([^"]+\.png)"', text)}


def main():
    con = sqlite3.connect("data/misterzine.sqlite"); con.row_factory = sqlite3.Row
    ours = {r["setname"].lower() for r in con.execute(
        "SELECT DISTINCT setname FROM catalog WHERE system='arcade' AND setname IS NOT NULL")}
    print(f"our arcade setnames: {len(ours)}\n")
    cover = {}
    for label, fn in PACKS.items():
        try:
            sets = {s.lower() for s in pack_setnames(BASE + fn)}
            hit = ours & sets
            cover[label] = hit
            print(f"{label:9s}: pack lists {len(sets):6d} sets | covers ours {len(hit):4d} ({100*len(hit)/len(ours):4.0f}%)")
        except Exception as e:
            print(f"{label:9s}: ERR {type(e).__name__} {str(e)[:90]}")
    secondary = [k for k in ("gameover", "scores", "select", "versus", "howto", "bosses") if k in cover]
    if secondary:
        union = set().union(*(cover[k] for k in secondary))
        print(f"\n>=1 secondary in-game shot: {len(union)} ({100*len(union)/len(ours):.0f}% of setnamed titles)")


if __name__ == "__main__":
    main()
