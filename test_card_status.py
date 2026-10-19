"""bd/bh: the shipped rbf's own build date and md5, untouched by the
`updated` adjustments (MRA-only fix bump, debut floor)."""
import unittest
from unittest import mock
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

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

    def test_ongo_regional_sets_fold_only_on_the_same_core(self):
        rows = [
            arcade(source_id="ongo", title="RayForce (Ver 2.3A)", setname="rayforce",
                   rbf="TaitoF3", path="_Arcade/_Taito F3 (WIP)/RayForce (Ver 2.3A).mra"),
            arcade(source_id="ongo", title="RayForce (Ver 2.3J)", setname="rayforcej",
                   rbf="TaitoF3", path="_Arcade/_Taito F3 (WIP)/RayForce (Ver 2.3J).mra"),
            arcade(source_id="ongo", title="RayForce (other core)", setname="rayforcej",
                   rbf="TaitoF3Experimental", path="_Arcade/_alternatives/RayForce (other core).mra"),
        ]
        meta = {"rayforce": {"parent": ""}, "rayforcej": {"parent": "rayforce"}}
        kept = mz.fold_sibling_variants(rows, meta)
        self.assertEqual([r["title"] for r in kept],
                         ["RayForce (Ver 2.3A)", "RayForce (other core)"])


class OngoSourceTests(unittest.TestCase):
    def test_visibility_accepts_database_rows_and_export_dicts(self):
        shipped = {"ongo": {"core_20261018": ("core", "core")}}
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        for source, rbf, visible in [
            ("ongo", "core", True),
            ("ongo", "other", False),
            ("ongo", None, False),
            ("ongo", "", False),
            ("distribution_mister", None, True),
        ]:
            row = con.execute("SELECT ? AS source_id, ? AS rbf", (source, rbf)).fetchone()
            for record in (row, dict(row)):
                with self.subTest(source=source, rbf=rbf, record_type=type(record)):
                    self.assertEqual(mz._source_row_visible(record, shipped), visible)

    def test_image_backfill_inherits_richer_art_for_same_setname(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            manifest_path = cache / "image_manifest.json"
            manifest_path.write_text(json.dumps([
                {"title": "Star Wars", "setname": "starwars", "source": "psnaps",
                 "title_img": "titles/starwars.png", "snap_img": "snap/starwars.png",
                 "third_img": "gameover/starwars.png", "third_pack": "gameover"},
                {"title": "Empire Strikes Back", "setname": "starwars", "source": "adb",
                 "title_img": "titles/starwars.png", "snap_img": "ingames/starwars.png",
                 "third_img": None, "third_pack": None},
                {"title": "Star Wars (Rev 2)", "setname": "starwars", "source": None,
                 "title_img": None, "snap_img": None, "third_img": None, "third_pack": None},
            ]), encoding="utf-8")
            with mock.patch.object(mz, "CACHEDIR", cache), \
                 mock.patch.object(mz, "DOCSDIR", root / "docs"), \
                 mock.patch.object(mz, "_fetch_png", side_effect=AssertionError("unexpected download")):
                mz._backfill_arcade_images([{"base": "Arcade", "title": "Star Wars (Rev 2)",
                                             "sn": "starwars", "date": "2026-10-18"}])
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            rev2 = next(e for e in saved if e["title"] == "Star Wars (Rev 2)")
            self.assertEqual(rev2["source"], "psnaps")
            self.assertEqual(rev2["third_img"], "gameover/starwars.png")
            self.assertEqual(rev2["third_pack"], "gameover")

    def test_scope_keeps_only_arcade_mras_and_shipped_core_files(self):
        allowed = ["_Arcade/Game.mra", "_Arcade/_Nintendo VS. System/Game.mra",
                   "_Arcade/cores/Core_20261018.rbf"]
        rejected = ["_Console/Game.mra", "_Arcade/cores/readme.txt",
                    "_Arcade/playlist.mgl", "_Arcade/games/rom.zip",
                    "_Arcade/_Cave CV1000/_Cave CV1000 Practice ROMs/Game.mra",
                    "Scripts/install.sh"]
        self.assertTrue(all(mz.tracked_path("ongo", p) for p in allowed))
        self.assertFalse(any(mz.tracked_path("ongo", p) for p in rejected))

    def test_enrichment_uses_full_paths_for_same_basename_and_filters_unshipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            paths = ["_Arcade/Clone A/Game.mra", "_Arcade/Clone B/Game.mra"]
            xml = [
                '<mister><rbf>CoreA</rbf><setname>set_a</setname><year>1981</year>'
                '<manufacturer>Maker A</manufacturer><rotation>horizontal</rotation></mister>',
                '<mister><rbf>CoreB</rbf><setname>set_b</setname><year>1982</year>'
                '<manufacturer>Maker B</manufacturer><rotation>vertical</rotation></mister>',
            ]
            for rel, contents in zip(paths, xml):
                file = repo / rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(contents, encoding="utf-8")

            dbpath = root / "catalog.sqlite"
            specpath = root / "mra_specs.json"
            with mock.patch.object(mz, "DBPATH", dbpath), \
                 mock.patch.object(mz, "MRA_SPECS_JSON", specpath), \
                 mock.patch.object(mz, "_ongo_mra_paths", return_value=paths), \
                 mock.patch.object(mz, "_sparse_arcade_clone", return_value=repo):
                con = mz.connect()
                for i, rel in enumerate(paths):
                    con.execute("INSERT INTO catalog(source_id,path,system,kind,title) "
                                "VALUES('ongo',?,'arcade','mra',?)",
                                (rel, f"Game {i}"))
                con.commit()
                con.close()
                mz.cmd_enrich_mra(type("Args", (), {"source": "ongo"})())

                con = mz.connect()
                rows = con.execute("SELECT path,year,manufacturer,rbf,setname FROM catalog "
                                   "WHERE source_id='ongo' ORDER BY path").fetchall()
                con.close()
                self.assertEqual([(r["year"], r["manufacturer"], r["rbf"], r["setname"])
                                  for r in rows],
                                 [("1981", "Maker A", "CoreA", "set_a"),
                                  ("1982", "Maker B", "CoreB", "set_b")])
                specs = json.loads(specpath.read_text(encoding="utf-8"))
                self.assertEqual(set(specs["ongo"]), set(paths))
                self.assertEqual(specs["ongo"][paths[0]]["rot"], "Horizontal")
                self.assertEqual(specs["ongo"][paths[1]]["rot"], "Vertical")

        # Existing sources deliberately retain their established basename join.
        self.assertEqual(mz._mra_metadata_key("rossops", "releases/Game.mra"), "Game.mra")
        shipped = {"ongo": {"core_20261018": ("core_20261018.rbf", "core")}}
        self.assertTrue(mz._source_row_visible(arcade(source_id="ongo", rbf="core"), shipped))
        self.assertFalse(mz._source_row_visible(arcade(source_id="ongo", rbf="other"), shipped))

    def test_ongo_core_identifier_keeps_install_key_and_original_repo(self):
        row = mz._web_row(
            arcade(source_id="ongo", rbf="Namco_NB1",
                   repo="kyledlester/Namco_NB1_MiSTer"),
            core_files={"namco_nb1": {"ongo": "2026-10-18"}},
            core_hashes={"namco_nb1": {"ongo": "ab" * 16}},
            shipped_rbfs={"ongo": {"namco_nb1_20261018":
                                   ("namco_nb1", "Namco_NB1")}})
        self.assertEqual(row["core"], "Namco_NB1")
        self.assertEqual(row["repo"], "kyledlester/Namco_NB1_MiSTer")
        self.assertEqual(row["bd"], "2026-10-18")
        self.assertEqual(row["bh"], "ab" * 16)

    def test_sparse_checkout_escapes_bracketed_mra_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = ["_Arcade/Alcon [v1.0].mra",
                        "_Arcade/_Nintendo VS. System/Game (Japan).mra"]
            extra = "_Arcade/scripts/install.sh"
            for rel in selected + [extra]:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("sample", encoding="utf-8")

            def git(*args, input_text=None):
                return subprocess.run(["git", "-C", str(root), *args], input=input_text,
                                      text=True, check=True, capture_output=True)

            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Test")
            git("add", "--all")
            git("commit", "-qm", "seed")
            git("sparse-checkout", "init", "--no-cone")
            git("sparse-checkout", "set", "--no-cone", "--stdin",
                input_text="\n".join(mz._sparse_checkout_patterns(selected)) + "\n")
            self.assertTrue(all((root / rel).exists() for rel in selected))
            self.assertFalse((root / extra).exists())


class RetitleKeyTests(unittest.TestCase):
    def test_build_stamp_is_not_part_of_the_name(self):
        self.assertEqual(mz._retitle_key("RevX_09132026"), mz._retitle_key("RevX_09302026"))

    def test_region_qualifiers_still_split(self):
        self.assertEqual(mz._retitle_key("Jungle King Japan"), mz._retitle_key("Jungle King (Japan)"))
        self.assertNotEqual(mz._retitle_key("Game (US)"), mz._retitle_key("Game (World)"))


class SameGameGroupTests(unittest.TestCase):
    """`g` folds one game on several cores; see attach_same_game_groups."""
    META = {"bublbobl": {"parent": ""}, "boblbobl": {"parent": "bublbobl"},
            "sprint1": {"parent": ""}, "sprint2": {"parent": "sprint1"}}

    @staticmethod
    def web(title, sn, src, core, mt=None):
        d = {"base": "Arcade", "title": title, "sn": sn, "src": src, "core": core}
        if mt:
            d["mt"] = mt
        return d

    def test_same_setname_groups_across_cores(self):
        data = [self.web("Bubble Bobble", "bublbobl", "jtbindb", "jtbubl"),
                self.web("Bubble Bobble (Japan) [CoC]", "bublbobl", "coinop", "bublbobl_mister")]
        self.assertEqual(mz.attach_same_game_groups(data, self.META), 1)
        self.assertEqual([d["g"] for d in data], ["bublbobl", "bublbobl"])

    def test_same_parent_and_base_title_groups(self):
        data = [self.web("Bubble Bobble", "bublbobl", "jtbindb", "jtbubl"),
                self.web("Bubble Bobble (bootleg)", "boblbobl", "meathax", "Arcade-Bobble")]
        mz.attach_same_game_groups(data, self.META)
        self.assertEqual([d.get("g") for d in data], ["bublbobl", "bublbobl"])

    def test_same_parent_different_base_title_stays_apart(self):
        data = [self.web("Sprint 1", "sprint1", "distribution_mister", "sprint1"),
                self.web("Sprint 2", "sprint2", "distribution_mister", "sprint2")]
        self.assertEqual(mz.attach_same_game_groups(data, self.META), 0)
        self.assertTrue(all("g" not in d for d in data))

    def test_one_core_variant_pair_stays_apart(self):
        data = [self.web("Asteroids Deluxe (green)", "astdelux", "distribution_mister", "Asteroids"),
                self.web("Asteroids Deluxe (orange)", "astdelux", "distribution_mister", "Asteroids")]
        self.assertEqual(mz.attach_same_game_groups(data, {}), 0)

    def test_raw_mt_title_wins_over_display_title(self):
        # a retitled row keeps its raw MRA title in mt; grouping reads that
        data = [self.web("Bubble Bobble (Jotego)", "bublbobl", "jtbindb", "jtbubl", mt="Bubble Bobble"),
                self.web("Bubble Bobble (Coin-Op)", "boblbobl", "coinop", "bb_mister", mt="Bubble Bobble")]
        mz.attach_same_game_groups(data, self.META)
        self.assertEqual(data[0]["g"], "bublbobl")

    def test_deterministic_regardless_of_input_order(self):
        rows = [self.web("Bubble Bobble", "bublbobl", "jtbindb", "jtbubl"),
                self.web("Bubble Bobble (Japan) [CoC]", "bublbobl", "coinop", "bublbobl_mister"),
                self.web("Sprint 1", "sprint1", "distribution_mister", "sprint1")]
        a = [dict(d) for d in rows]
        b = [dict(d) for d in reversed(rows)]
        mz.attach_same_game_groups(a, self.META)
        mz.attach_same_game_groups(b, self.META)
        self.assertEqual(sorted((d["title"], d.get("g")) for d in a),
                         sorted((d["title"], d.get("g")) for d in b))
