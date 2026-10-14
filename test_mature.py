"""Mature flag: catver's marker, the parent fallback and the hand pins."""
import unittest
import misterzine as mz
from test_card_status import arcade

CATVER = """[FOLDER_SETTINGS]
RootFolderIcon mame

[Category]
galpanic=Puzzle / Outline * Mature *
galaga=Shooter / Gallery
srmvs=Tabletop / Mahjong
"""


class MatureTests(unittest.TestCase):
    def test_parse_reads_only_the_marker(self):
        self.assertEqual(mz.parse_catver_mature(CATVER), {"galpanic"})
        # the genre parser still collapses the category as before
        self.assertEqual(mz.parse_catver(CATVER)["galpanic"], "Puzzle")

    def test_rules(self):
        mature = mz.parse_catver_mature(CATVER)
        cats = mz.parse_catver(CATVER)
        dat = {"galpanica": {"parent": "galpanic"}, "galagab": {"parent": "galaga"}}
        for sn, want in [("GALPANIC", True), ("galaga", False), ("", False),
                         ("galpanica", True),   # not in catver: parent's marker
                         ("galagab", False),
                         ("srmvs", True)]:      # MATURE_OVERRIDES pin beats catver
            with self.subTest(sn=sn):
                self.assertEqual(mz.mature_for(sn, mature, cats, dat), want)

    def test_export_adds_only_mat(self):
        mature = mz.parse_catver_mature(CATVER)
        cats = mz.parse_catver(CATVER)
        before = mz._web_row(arcade(setname="galpanic", title="Gals Panic"), arcade_cats=cats)
        after = mz._web_row(arcade(setname="galpanic", title="Gals Panic"), arcade_cats=cats,
                            arcade_mature=mature)
        self.assertEqual(after.pop("mat"), 1)
        self.assertEqual(before, after)
        plain = mz._web_row(arcade(setname="galaga", title="Galaga"), arcade_cats=cats,
                            arcade_mature=mature)
        self.assertNotIn("mat", plain)


if __name__ == "__main__":
    unittest.main()
