"""bd/bh: the shipped rbf's own build date and md5, untouched by the
`updated` adjustments (MRA-only fix bump, debut floor)."""
import unittest

import misterzine as mz


def catalog_row(**over):
    row = {key: "" for key in ["beta", "first_seen", "genre", "hash", "last_changed",
        "last_update", "manufacturer", "path", "rbf", "release_date", "setname",
        "source_id", "system", "title", "year"]}
    row.update({"beta": False, "source_id": "distribution_mister", **over})
    return row


def arcade(**over):
    return catalog_row(**{"system": "arcade", "title": "Unit", "setname": "unit",
                          "path": "_Arcade/Unit.mra", "rbf": "Unit", **over})


class CardStatusFieldTests(unittest.TestCase):
    def test_mra_fix_bumps_updated_but_not_bd(self):
        # Boogie Wings: rbf built Jul 8, MRA fixed Aug 8
        row = mz._web_row(
            arcade(release_date="2026-06-14", first_seen="2026-07-04T19:53:04+00:00",
                   last_changed="2026-08-08T16:32:49+00:00", last_update="2026-08-08T16:20:59Z"),
            core_files={"unit": {"distribution_mister": "2026-07-08"}},
            core_hashes={"unit": {"distribution_mister": "aa" * 16}})
        self.assertEqual(row["updated"], "2026-08-08")
        self.assertEqual(row["bd"], "2026-07-08")
        self.assertEqual(row["bh"], "aa" * 16)

    def test_debut_floor_leaves_bd_raw(self):
        # Coin-Op Boogie Wings: file dated Jul 29, debut commit Jul 30 UTC
        row = mz._web_row(
            arcade(source_id="coinop", release_date="2026-07-30"),
            core_files={"unit": {"coinop": "2026-07-29"}},
            core_hashes={"unit": {"coinop": "bb" * 16}})
        self.assertEqual(row["updated"], "2026-07-30")
        self.assertEqual(row["bd"], "2026-07-29")

    def test_undated_rbf_ships_hash_only(self):
        row = mz._web_row(
            arcade(source_id="jtbindb", rbf="jt1942", release_date="2020-01-01",
                   last_update="2026-09-01T00:00:00Z"),
            core_files={}, core_hashes={"jt1942": {"jtbindb": "cc" * 16}})
        self.assertNotIn("bd", row)
        self.assertEqual(row["bh"], "cc" * 16)

    def test_foreign_source_file_prefers_newest_dated(self):
        row = mz._web_row(
            arcade(source_id="coinop", release_date="2026-01-01"),
            core_files={"unit": {"a": "2026-02-01", "b": "2026-03-01"}},
            core_hashes={"unit": {"a": "a" * 32, "b": "b" * 32}})
        self.assertEqual(row["bd"], "2026-03-01")
        self.assertEqual(row["bh"], "b" * 32)

    def test_no_core_file_omits_fields(self):
        row = mz._web_row(arcade(release_date="2026-01-01"), core_files={}, core_hashes={})
        self.assertNotIn("bd", row)
        self.assertNotIn("bh", row)

    def test_system_core_uses_own_filename_and_hash(self):
        row = mz._web_row(catalog_row(system="console", kind="core", title="NES_20260601",
                                      path="_Console/NES_20260601.rbf", hash="dd" * 16,
                                      release_date="2018-01-01T00:00:00Z"))
        self.assertEqual(row["bd"], "2026-06-01")
        self.assertEqual(row["bh"], "dd" * 16)
        self.assertEqual(row["updated"], "2026-06-01")


if __name__ == "__main__":
    unittest.main()


class ShippedRbfResolutionTests(unittest.TestCase):
    """MRA <rbf> tags resolve to the db's shipped file the way MiSTer's loader
    does (prefix + `_`/`.`, greatest filename wins); issues #9/#10."""
    shipped = {"coinop": {
        "blkheart_mister_20260909": ("blkheart_mister", "blkheart_mister"),
        "zerowing_20240404": ("zerowing", "zerowing"),
        "zerowing_mister_20251119": ("zerowing_mister", "zerowing_mister"),
        "tdragon_mister_20260908": ("tdragon_mister", "tdragon_mister"),
    }, "meathax": {
        "arcade-bucky_20260812": ("arcade-bucky", "Arcade-Bucky"),
    }}

    def test_prefix_tag_exports_shipped_stem_and_joins_build(self):
        row = mz._web_row(
            arcade(source_id="coinop", rbf="blkheart", release_date="2026-09-09"),
            core_files={"blkheart_mister": {"coinop": "2026-09-09"}},
            core_hashes={"blkheart_mister": {"coinop": "dd" * 16}},
            shipped_rbfs=self.shipped)
        self.assertEqual(row["core"], "blkheart_mister")
        self.assertEqual(row["bd"], "2026-09-09")
        self.assertEqual(row["bh"], "dd" * 16)

    def test_exact_core_tag_is_untouched(self):
        self.assertEqual(mz._resolve_shipped_rbf("coinop", "Zerowing_Mister", self.shipped),
                         ("Zerowing_Mister", "zerowing_mister"))

    def test_dated_pin_keeps_its_name_but_keys_the_core(self):
        # Out Zone pins zerowing_20240404; the card file IS that stem, the
        # build-date join is on the zerowing core
        self.assertEqual(mz._resolve_shipped_rbf("coinop", "zerowing_20240404", self.shipped),
                         ("zerowing_20240404", "zerowing"))

    def test_named_core_beats_longer_sibling(self):
        # a bare 'zerowing' tag names a shipped core outright, so it stays that
        # core (key-stable for every existing row) even though MiSTer's
        # greatest-filename tie-break would load zerowing_mister_* from a card
        # holding both; the prefix walk only runs when the tag names nothing
        self.assertEqual(mz._resolve_shipped_rbf("coinop", "zerowing", self.shipped),
                         ("zerowing", "zerowing"))

    def test_prefix_picks_greatest_filename_like_mister(self):
        shipped = {"x": {"foo_a_20250101": ("foo_a", "foo_a"), "foo_b_20240101": ("foo_b", "foo_b")}}
        self.assertEqual(mz._resolve_shipped_rbf("x", "foo", shipped), ("foo_b", "foo_b"))

    def test_prefix_needs_separator(self):
        # 'tdrago' is not a prefix match: MiSTer wants `_` or `.` right after
        self.assertIsNone(mz._resolve_shipped_rbf("coinop", "tdrago", self.shipped))

    def test_arcade_prefixed_file(self):
        self.assertEqual(mz._resolve_shipped_rbf("meathax", "bucky", self.shipped),
                         ("Arcade-Bucky", "arcade-bucky"))

    def test_unshipped_and_unknown_source_resolve_to_none(self):
        self.assertIsNone(mz._resolve_shipped_rbf("coinop", "captaven", self.shipped))
        self.assertIsNone(mz._resolve_shipped_rbf("jtbindb", "jt1942", self.shipped))
        row = mz._web_row(arcade(source_id="coinop", rbf="captaven", release_date="2026-07-05"),
                          core_files={}, core_hashes={}, shipped_rbfs=self.shipped)
        self.assertEqual(row["core"], "captaven")
        self.assertNotIn("bd", row)


class DuplicateTitleTests(unittest.TestCase):
    def test_exact_duplicates_only(self):
        data = [{"title": "Black Heart", "src": "coinop", "core": "blkheart_mister", "sn": "blkheart"},
                {"title": "Black Heart", "src": "kuzecores", "core": "Arcade-NMK16_Gunnail", "sn": "blkheart"},
                {"title": "Thunder Dragon", "src": "kuzecores"},
                {"title": "Thunder Dragon (8th Jan. 1992)", "src": "coinop"},
                {"title": "", "src": "x"}, {"title": "", "src": "y"}]
        dupes = mz.duplicate_titles(data)
        self.assertEqual(list(dupes), ["Black Heart"])
        self.assertEqual([d["src"] for d in dupes["Black Heart"]], ["coinop", "kuzecores"])

    def test_clean_export_has_none(self):
        self.assertEqual(mz.duplicate_titles([{"title": "A"}, {"title": "B"}]), {})


class SiblingVariantFoldTests(unittest.TestCase):
    META = {"nslasher": {"parent": None}, "nslasherj": {"parent": "nslasher"},
            "nslashers": {"parent": "nslasher"}, "nbahangt": {"parent": None},
            "nbamht": {"parent": "nbahangt"}, "mk": {"parent": None}}

    def blahm1d(self, title, sn, rbf):
        return arcade(source_id="blahm1d", title=title, setname=sn, rbf=rbf,
                      path=f"_Arcade/_blahm1d/{rbf}/{title}.mra")

    def test_region_sets_fold_to_the_parent(self):
        rows = [self.blahm1d("Night Slashers (Japan Rev 1.2)", "nslasherj", "blahm1d_ns"),
                self.blahm1d("Night Slashers (Korea Rev 1.3)", "nslasher", "blahm1d_ns"),
                self.blahm1d("Night Slashers (Over Sea Rev 1.2)", "nslashers", "blahm1d_ns")]
        kept = mz.fold_sibling_variants(rows, self.META)
        self.assertEqual([r["setname"] for r in kept], ["nslasher"])

    def test_distinct_names_and_cores_stay(self):
        rows = [self.blahm1d("NBA Hangtime (L1.3)", "nbahangt", "blahm1d_wolfunit"),
                self.blahm1d("NBA Maximum Hangtime (L1.03)", "nbamht", "blahm1d_wolfunit"),
                self.blahm1d("Mortal Kombat (rev 5.0 T-Unit)", "mk", "blahm1d_tunit"),
                self.blahm1d("Mortal Kombat (rev 4.0, Y-Unit)", "mk", "blahm1d_yunitadpcm")]
        self.assertEqual(len(mz.fold_sibling_variants(rows, self.META)), 4)

    def test_other_sources_are_untouched(self):
        # the Distribution's two Asteroids Deluxe colours are a deliberate pair
        rows = [arcade(title="Asteroids Deluxe (v3 green)", setname="astdelux", path="a"),
                arcade(title="Asteroids Deluxe (v3 orange)", setname="astdelux", path="b")]
        self.assertEqual(len(mz.fold_sibling_variants(rows, {"astdelux": {}})), 2)


class RetitleKeyTests(unittest.TestCase):
    def test_build_stamp_is_not_part_of_the_name(self):
        self.assertEqual(mz._retitle_key("RevX_09132026"), mz._retitle_key("RevX_09302026"))

    def test_region_qualifiers_still_split(self):
        self.assertEqual(mz._retitle_key("Jungle King Japan"), mz._retitle_key("Jungle King (Japan)"))
        self.assertNotEqual(mz._retitle_key("Game (US)"), mz._retitle_key("Game (World)"))
