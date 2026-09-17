"""tools/seed_r2.py: the pure parts (keys, maps, upload planning, PNG dims)."""
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
import seed_r2  # noqa: E402


def tiny_png(w=2, h=1):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"\x00" + b"\xff\x00\x00" * w
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class SeedR2Test(unittest.TestCase):
    def test_setname_keys(self):
        self.assertEqual(seed_r2.setname_of("dkong.png"), "dkong")
        self.assertEqual(seed_r2.setname_of("C:/stage/snap/005.png"), "005")
        self.assertEqual(seed_r2.setname_of("a" * 32 + ".PNG"), "a" * 32)
        for bad in ("DKong.png", "dkong.jpg", "dk ong.png", "a" * 33 + ".png", "sf-2.png", ".png"):
            self.assertIsNone(seed_r2.setname_of(bad), bad)

    def test_meta_maps(self):
        meta = {
            "dkong": {"parent": "", "desc": "Donkey Kong (US set 1)"},
            "dkongj": {"parent": "dkong", "desc": "Donkey Kong (Japan set 1)"},
            "weird": {"parent": "weird", "desc": ""},
        }
        parents, descs = seed_r2.meta_maps(meta)
        self.assertEqual(parents, {"dkongj": "dkong"})
        self.assertEqual(descs, {"dkong": "Donkey Kong (US set 1)", "dkongj": "Donkey Kong (Japan set 1)"})

    def test_plan_uploads(self):
        files = [("snap/a.png", "a"), ("snap/b.png", "b")]
        self.assertEqual(seed_r2.plan_uploads(files, {"snap/a.png": "etag"}), [("snap/b.png", "b")])
        self.assertEqual(seed_r2.plan_uploads(files, {"snap/a.png": "etag"}, force=True), files)
        self.assertEqual(seed_r2.plan_uploads(files, {}), files)

    def test_png_dims_and_md5(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.png")
            with open(p, "wb") as f:
                f.write(tiny_png(240, 292))
            self.assertEqual(seed_r2.png_dims(p), (240, 292))
            self.assertEqual(len(seed_r2.md5_of(p)), 32)
            with open(p, "wb") as f:
                f.write(b"<html>")
            self.assertNotEqual(seed_r2.png_dims(p), (240, 292))

    def test_site_files_filters_slugs(self):
        files = seed_r2.site_files("snap")
        self.assertTrue(all(k.startswith("snap/") for k, _ in files))
        for k, _ in files:
            self.assertRegex(k[len("snap/"):-4], seed_r2.SETNAME_RE)


if __name__ == "__main__":
    unittest.main()
