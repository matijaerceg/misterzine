"""Game-family export is explicit, stable and optional."""
import unittest
import misterzine as mz
from test_card_status import arcade

class FamilyTests(unittest.TestCase):
    def test_ancestry(self):
        meta = {"galagamw": {"parent": "galaga"}, "galaga": {},
                "child": {"parent": "galagamw"}, "self": {"parent": "self"},
                "broken": {"parent": "missing"}, "a": {"parent": "b"}, "b": {"parent": "a"}}
        for name, want in [("GALAGAMW", "galaga"), ("child", "galaga"),
                           ("galaga", "galaga"), ("self", "self"),
                           ("missing", ""), ("broken", ""), ("a", ""), ("", "")]:
            with self.subTest(name=name):
                self.assertEqual(mz.arcade_family(name, meta), want)

    def test_export_changes_only_family(self):
        source = arcade(setname="galagamw", title="Galaga")
        before = mz._web_row(source)
        after = mz._web_row(source, arcade_meta={"galagamw": {"parent": "galaga"}, "galaga": {}})
        self.assertEqual(after.pop("family"), "galaga")
        self.assertEqual(after.pop("family_sets"), ["galagamw"])
        self.assertEqual(before, after)
        self.assertNotIn("family", mz._web_row(source, arcade_meta={}))

    def test_members_exclude_unrelated_and_invalid_sets(self):
        meta = {"root": {}, "child": {"parent": "root"}, "other": {}, "bad": {"parent": "missing"}}
        self.assertEqual(mz.arcade_family_members(meta), {"root": ["child"]})

    def test_non_arcade_omits_family(self):
        from test_card_status import catalog_row
        row = catalog_row(system="console", kind="core", title="NES", path="_Console/NES.rbf")
        self.assertNotIn("family", mz._web_row(row, arcade_meta={"nes": {}}))

    def test_no_title_inference(self):
        self.assertNotIn("family", mz._web_row(arcade(setname="unknown", title="Galaga"),
                                              arcade_meta={"galaga": {}}))

if __name__ == "__main__":
    unittest.main()
