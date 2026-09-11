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
