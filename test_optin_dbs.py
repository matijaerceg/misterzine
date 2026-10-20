"""The site's opt-in db list (OPTIN_DBS) must match the pipeline's SOURCES.

The Source menu's downloader.ini lines and every opt-in panel note print
OPTIN_DBS' db_url, so a db that moves in misterzine.py and not in the page
would hand visitors a dead line.
"""
import re
import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
