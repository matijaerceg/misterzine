"""The site's opt-in db list (OPTIN_DBS) must match the pipeline's SOURCES.

The Source menu's downloader.ini lines and every opt-in panel note print
OPTIN_DBS' db_url, so a db that moves in misterzine.py and not in the page
would hand visitors a dead line.
"""
import json
import re
import unittest
from pathlib import Path
from unittest import mock
import misterzine as mz

PAGE = (Path(__file__).parent / "docs" / "releases" / "index.html").read_text(encoding="utf-8")


def js_block(name):
    m = re.search(r"const " + name + r" = (?:new Set\(\[|\{)(.*?)\n(?:\}|\]\));", PAGE, re.S)
    assert m, name
    return m.group(1)


OPTIN = {k: (sec, url) for k, sec, url in re.findall(
    r"^  (\w+): \{\s*section: '([^']+)',\s*url: '([^']+)'", js_block("OPTIN_DBS"), re.M)}
BUNDLED = set(re.findall(r"'(\w+)'", js_block("UPDATE_ALL_INCLUDED")))
FT_SECTIONS = dict(re.findall(r"^  (\w+): '([^']+)'", js_block("FT_SECTIONS"), re.M))


class OptinDbTests(unittest.TestCase):
    def test_every_source_is_bundled_or_optin(self):
        ids = {s["id"] for s in mz.SOURCES}
        self.assertEqual(ids, BUNDLED | set(OPTIN))
        self.assertFalse(BUNDLED & set(OPTIN))

    def test_urls_match_sources(self):
        urls = {s["id"]: s["db_url"] for s in mz.SOURCES}
        for k, (_, url) in OPTIN.items():
            with self.subTest(src=k):
                self.assertEqual(url, urls[k])

    def test_sections_match_export_dialog(self):
        for k, (sec, _) in OPTIN.items():
            with self.subTest(src=k):
                self.assertEqual(sec, FT_SECTIONS[k])


class InstallRootTests(unittest.TestCase):
    """RodimusFVC's db installs to _RodimusCores/, not _Arcade/: read in the
    _Arcade/ shape, exported (the launch button's path) as installed."""

    def test_paths_read_in_arcade_shape(self):
        m = mz._rodimus_path
        self.assertEqual(m("_RodimusCores/_Arcade/Frogs.mra"), "_Arcade/Frogs.mra")
        self.assertEqual(m("_RodimusCores/_Arcade/_alternatives/_Head On/Head On (2P).mra"),
                         "_Arcade/_alternatives/_Head On/Head On (2P).mra")
        self.assertEqual(m("_RodimusCores/cores/SegaVICDual_TestBuild.rbf"),
                         "_Arcade/cores/SegaVICDual_TestBuild.rbf")
        self.assertEqual(m("_RodimusCores/_InteractiveFiction/cores/Frotz_20261022.rbf"),
                         "_Other/Frotz_20261022.rbf")
        self.assertEqual(m("_RodimusCores/cores/Robots_20260925.rbf"), "_Other/Robots_20260925.rbf")

    def test_unlisted_files_drop(self):
        for path in ("_RodimusCores/_Arcade/_artwork/Frogs.mra",
                     "_RodimusCores/_Arcade/_artwork/_alternatives/_Xevious/Xevious (Atari, Set 4).mra",
                     "_RodimusCores/_Arcade/Not Working/GP World.mra",
                     "_RodimusCores/_InteractiveFiction/Zork I.mgl",
                     "_RodimusCores/_VCR/Isaac Asimov's Robots.mra",
                     "_Arcade/Frogs.mra"):
            with self.subTest(path=path):
                self.assertIsNone(mz._rodimus_path(path))

    def test_mapped_paths_classify_like_any_db(self):
        self.assertEqual(mz.classify("_Arcade/Frogs.mra"), ("arcade", "title", True))
        self.assertEqual(mz.classify("_Arcade/cores/Galaga_20261114.rbf")[:2], ("arcade", "support"))
        self.assertEqual(mz.classify("_Other/Frotz_20261022.rbf"), ("other", "core", True))

    def test_export_path_is_the_install_path(self):
        self.assertEqual(mz.sd_path("rodimus", "_Arcade/Frogs.mra"), "_RodimusCores/_Arcade/Frogs.mra")
        self.assertEqual(mz.sd_path("distribution_mister", "_Arcade/Frogs.mra"), "_Arcade/Frogs.mra")

    def test_load_db_remaps_only_that_source(self):
        db = {"db_id": "x", "files": {
            "_RodimusCores/_Arcade/Frogs.mra": {"hash": "a"},
            "_RodimusCores/_Arcade/_artwork/Frogs.mra": {"hash": "b"},
            "_RodimusCores/cores/SegaVICDual_TestBuild.rbf": {"hash": "c"}}}
        raw = json.dumps(db).encode()
        with mock.patch.object(mz, "http_get", return_value=raw):
            mapped = mz._load_db({"id": "rodimus", "db_url": "u"})
            plain = mz._load_db({"id": "ppriest", "db_url": "u"})
        self.assertEqual(sorted(mapped["files"]),
                         ["_Arcade/Frogs.mra", "_Arcade/cores/SegaVICDual_TestBuild.rbf"])
        self.assertEqual(mapped["files"]["_Arcade/Frogs.mra"], {"hash": "a"})
        self.assertEqual(plain["files"], db["files"])


if __name__ == "__main__":
    unittest.main()
