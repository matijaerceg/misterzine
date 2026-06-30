"""Probe progettoSNAPS secondary packs for third-screenshot coverage.

Reads each pack zip's central directory over HTTP Range (no image payload
download) to list setnames, then intersects with our arcade setnames.
"""
import urllib.request, struct, io, sqlite3, sys

BASE = "https://www.progettosnaps.net/snapshots/packs/full_sets/"
PACKS = {
    "gameover": "pS_gameover_fullset_270.zip",
    "scores":   "pS_scores_fullset_270.zip",
    "select":   "pS_select_fullset_270.zip",
    "versus":   "pS_versus_fullset_270.zip",
    "howto":    "pS_howto_fullset_270.zip",
    "bosses":   "pS_bosses_fullset_270.zip",
}
EOCD_SIG = b"\x50\x4b\x05\x06"


def rng(url, start, end=None):
    h = {"User-Agent": "Mozilla/5.0 misterzine-probe",
         "Range": f"bytes={start}-" + ("" if end is None else str(end))}
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60)


def head_len(url):
    r = urllib.request.urlopen(urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 misterzine-probe"}), timeout=30)
    return int(r.headers["Content-Length"]), r.headers.get("Accept-Ranges")


def list_zip_names(url):
    """Return list of member names by reading the central directory via Range."""
    size, ar = head_len(url)
    tail = min(size, 1 << 16)
    buf = rng(url, size - tail).read()
    p = buf.rfind(EOCD_SIG)
    if p < 0:
        raise RuntimeError("EOCD not found (zip64?)")
    total, cd_size, cd_off = struct.unpack("<H", buf[p+10:p+12])[0], \
        struct.unpack("<I", buf[p+12:p+16])[0], struct.unpack("<I", buf[p+16:p+20])[0]
    cd = rng(url, cd_off, cd_off + cd_size - 1).read()
    names, i = [], 0
    while i + 46 <= len(cd) and cd[i:i+4] == b"\x50\x4b\x01\x02":
        nlen, elen, clen = struct.unpack("<HHH", cd[i+28:i+34])
        name = cd[i+46:i+46+nlen].decode("utf-8", "ignore")
        names.append(name)
        i += 46 + nlen + elen + clen
    return size, total, names


def setnames_from(names):
    out = set()
    for n in names:
        if n.lower().endswith(".png"):
            out.add(n.rsplit("/", 1)[-1][:-4].lower())
    return out


def main():
    con = sqlite3.connect("data/misterzine.sqlite"); con.row_factory = sqlite3.Row
    ours = {r["setname"].lower() for r in con.execute(
        "SELECT DISTINCT setname FROM catalog WHERE system='arcade' AND setname IS NOT NULL")}
    print(f"our arcade setnames: {len(ours)}\n")
    print(f"{'pack':10s} {'zipMB':>7s} {'files':>7s} {'covers ours':>12s}")
    cover = {}
    for label, fn in PACKS.items():
        url = BASE + fn
        try:
            size, total, names = list_zip_names(url)
            sets = setnames_from(names)
            hit = ours & sets
            cover[label] = hit
            print(f"{label:10s} {size/1e6:7.0f} {total:7d} {len(hit):6d} ({100*len(hit)/len(ours):4.0f}%)")
        except Exception as e:
            print(f"{label:10s}  ERR {type(e).__name__} {str(e)[:80]}")
    # union: titles that get AT LEAST ONE secondary in-game shot
    if cover:
        union = set().union(*cover.values())
        print(f"\nat least one secondary shot: {len(union)} ({100*len(union)/len(ours):.0f}% of our setnamed titles)")


if __name__ == "__main__":
    main()
