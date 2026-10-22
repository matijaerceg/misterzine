"""Future build dates: a row's shown Build Date is capped at the day the
tracker first saw that build (row_batches stamp) plus one day of grace."""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import misterzine as mz


class CapTests(unittest.TestCase):
    def test_two_days_ahead_is_capped_to_stamp_plus_grace(self):
        self.assertEqual(mz._cap_future_build("2026-10-23", "2026-10-21T08:00:00+00:00"), "2026-10-22")

    def test_one_day_ahead_is_kept_as_typed(self):
        self.assertEqual(mz._cap_future_build("2026-10-22", "2026-10-21T08:00:00+00:00"), "2026-10-22")

    def test_past_and_same_day_untouched(self):
        self.assertEqual(mz._cap_future_build("2026-10-21", "2026-10-21T08:00:00+00:00"), "2026-10-21")
        self.assertEqual(mz._cap_future_build("2024-05-17", "2026-10-21T08:00:00+00:00"), "2024-05-17")

    def test_missing_values_pass_through(self):
        self.assertEqual(mz._cap_future_build("", "2026-10-21"), "")
        self.assertIsNone(mz._cap_future_build(None, "2026-10-21"))
        self.assertEqual(mz._cap_future_build("2026-10-23", None), "2026-10-23")


class AssignBatchesTests(unittest.TestCase):
    def _run(self, data, stored=(), now="2026-10-21T08:00:00+00:00"):
        # the function closes its connection, so the table lives in a temp file
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        def connect():
            con = sqlite3.connect(tmp.name)
            con.row_factory = sqlite3.Row
            con.executescript("CREATE TABLE IF NOT EXISTS row_batches (k TEXT PRIMARY KEY, "
                              "updated TEXT, batch INTEGER, stamped_at TEXT);")
            return con
        con = connect()
        con.executemany("INSERT INTO row_batches VALUES(?,?,?,?)", stored)
        con.commit(); con.close()
        with mock.patch.object(mz, "connect", connect), \
             mock.patch.object(mz, "now_iso", return_value=now), \
             mock.patch.object(mz, "log"):
            mz._assign_update_batches(data)
        return connect()

    def test_new_row_capped_but_stored_raw(self):
        data = [{"k": "semi", "title": "Cookie", "core": "TomSVR_semicom", "updated": "2026-10-23"}]
        con = self._run(data)
        self.assertEqual(data[0]["updated"], "2026-10-22")
        row = con.execute("SELECT updated, batch FROM row_batches WHERE k='semi'").fetchone()
        self.assertEqual((row["updated"], row["batch"]), ("2026-10-23", 1))

    def test_stored_row_is_not_restamped_and_cap_uses_its_stamp(self):
        # seen 10-21 (batch 7); a later run on 10-25 must keep batch 7 and the 10-22 cap
        data = [{"k": "semi", "title": "Cookie", "core": "TomSVR_semicom", "updated": "2026-10-23"}]
        con = self._run(data, stored=[("semi", "2026-10-23", 7, "2026-10-21T08:00:00+00:00")],
                        now="2026-10-25T08:00:00+00:00")
        self.assertEqual(data[0]["updated"], "2026-10-22")
        self.assertEqual(data[0]["b"], 7)
        self.assertEqual(con.execute("SELECT count(*) FROM row_batches").fetchone()[0], 1)

    def test_ordinary_row_untouched(self):
        data = [{"k": "x", "title": "X", "core": "X", "updated": "2026-10-20"}]
        self._run(data)
        self.assertEqual(data[0]["updated"], "2026-10-20")
        self.assertEqual(data[0]["b"], 1)


if __name__ == "__main__":
    unittest.main()
