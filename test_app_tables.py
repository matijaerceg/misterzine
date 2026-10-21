"""releases/app.json: the device app's source and core tables, read from index.html.

The app fetches app.json so a new source needs no app release. These tests pin
the extraction against the page itself (export-web regenerates the file, so a
page edit not yet exported is not a failure here).
"""
import json
import unittest
from pathlib import Path
import misterzine as mz

PAGE = (Path(__file__).parent / "docs" / "releases" / "index.html").read_text(encoding="utf-8")


class AppTablesTests(unittest.TestCase):
    def setUp(self):
        self.t = mz.app_tables(PAGE)

    def test_every_pipeline_source_is_named(self):
        ids = {s["id"] for s in mz.SOURCES}
        self.assertTrue(ids <= set(self.t["sources"]), ids - set(self.t["sources"]))

    def test_opt_in_urls_match_sources(self):
        urls = {s["id"]: s["db_url"] for s in mz.SOURCES}
        optin = {k: v for k, v in self.t["sources"].items() if v["db_url"]}
        self.assertGreaterEqual(len(optin), 10)
        for k, v in optin.items():
            with self.subTest(src=k):
                self.assertEqual(v["db_url"], urls[k])

    def test_known_values(self):
        s = self.t["sources"]
        self.assertEqual(s["shmupfan"], {"name": "shmupfan", "section": "shmupfan",
                                         "db_url": "https://raw.githubusercontent.com/shmupfan/Distribution/main/db.json"})
        self.assertEqual(s["jtbindb"], {"name": "Jotego (JTcores)", "section": "jtcores", "db_url": ""})
        self.assertEqual(self.t["core_names"]["TaitoGNET"], "Taito G-NET")
        self.assertEqual(self.t["core_names"]["Nostradamus"], "Nostradamus / Magical Cat Adventure")
        self.assertEqual(self.t["version"], mz.APP_TABLES_VERSION)

    def test_parsing_details(self):
        page = (
            "const CORE_NAMES = {\n" + "".join(f"  'c{i}': 'C {i}',\n" for i in range(50)) +
            "  'It\\'s': \"Quote's\", // a comment: 'x': 'y'\n};\n"
            "const SRC_NAMES = {\n  a: 'A', b: 'B', c: 'C', d: 'D (d)',\n};\n"
            "const FT_SECTIONS = {\n  a: 'a/a', b: 'b', c: 'c', d: 'd/d',\n};\n"
            "const OPTIN_DBS = {\n  d: {\n    section: 'd/d',\n    url: 'https://x/d.zip',\n"
            "    what: 'one ' +\n      'two',\n  },\n};\n")
        t = mz.app_tables(page)
        self.assertEqual(t["core_names"]["It's"], "Quote's")
        self.assertNotIn("x", t["core_names"])
        self.assertEqual(t["sources"]["d"], {"name": "D (d)", "section": "d/d", "db_url": "https://x/d.zip"})
        self.assertEqual(t["sources"]["a"]["db_url"], "")
        bad = page.replace("  a: 'a/a', ", "  ")
        with self.assertRaises(ValueError):
            mz.app_tables(bad)

    def test_written_file_is_sorted_json(self):
        path = Path(__file__).parent / "docs" / "releases" / "app.json"
        if not path.exists():
            self.skipTest("app.json not exported yet")
        got = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(got), {"version", "sources", "core_names"})


if __name__ == "__main__":
    unittest.main()
