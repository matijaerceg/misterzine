"""The hardware badge file (data/badges.json): what export-web accepts, what
stops it, and what it stamps on the rows."""
import json
import tempfile
import unittest
from pathlib import Path

import misterzine as mz


def row(**over):
    r = {"k": "gng", "title": "Ghosts'n Goblins", "base": "Arcade", "core": "jtgng", "sn": "gng"}
    r.update(over)
    return r


def badge(**over):
    b = {"k": "gng", "title": "Ghosts'n Goblins", "rbfs": ["jtgng"], "setnames": ["gng"],
         "granted": "2026-10-07", "proposed_by": "misterzine",
         "reason": "Built from the original schematics.", "links": ["https://example.org/gng"]}
    b.update(over)
    return b


def doc(*badges):
    return {"version": 1, "badges": list(badges)}


class BadgeProblems(unittest.TestCase):
    def test_matching_entry_is_clean(self):
        self.assertEqual(mz.badge_problems(doc(badge()), [row()]), [])

    def test_empty_list_is_clean(self):
        self.assertEqual(mz.badge_problems(doc(), [row()]), [])

    def test_stale_key_fails(self):
        probs = mz.badge_problems(doc(badge(k="gone")), [row()])
        self.assertEqual(len(probs), 1)
        self.assertIn("no row", probs[0])

    def test_wrong_rbf_fails(self):
        probs = mz.badge_problems(doc(badge(rbfs=["jt1942"])), [row()])
        self.assertTrue(any("rbfs lists 'jt1942'" in p for p in probs))
        self.assertTrue(any("must list the row's core 'jtgng'" in p for p in probs))

    def test_wrong_setname_fails(self):
        probs = mz.badge_problems(doc(badge(setnames=["makaimur"])), [row()])
        self.assertTrue(any("setnames lists 'makaimur'" in p for p in probs))

    def test_empty_names_fail_when_the_row_has_them(self):
        probs = mz.badge_problems(doc(badge(rbfs=[], setnames=[])), [row()])
        self.assertEqual(len(probs), 2)

    def test_row_without_setname_needs_none(self):
        self.assertEqual(mz.badge_problems(doc(badge(setnames=[])), [row(sn=None)]), [])

    def test_non_arcade_row_fails(self):
        probs = mz.badge_problems(doc(badge()), [row(base="Console")])
        self.assertTrue(any("not an arcade game" in p for p in probs))

    def test_duplicate_key_fails(self):
        probs = mz.badge_problems(doc(badge(), badge()), [row()])
        self.assertTrue(any("twice" in p for p in probs))

    def test_typo_field_fails(self):
        b = badge()
        b["setname"] = b.pop("setnames")
        probs = mz.badge_problems(doc(b), [row()])
        self.assertTrue(any("missing setnames" in p for p in probs))
        self.assertTrue(any("unknown field(s) setname" in p for p in probs))

    def test_bad_date_and_links_fail(self):
        probs = mz.badge_problems(doc(badge(granted="2026-13-01", links=["ftp://x"])), [row()])
        self.assertTrue(any("granted" in p for p in probs))
        self.assertTrue(any("links" in p for p in probs))

    def test_empty_reason_fails(self):
        probs = mz.badge_problems(doc(badge(reason="  ")), [row()])
        self.assertTrue(any("reason" in p for p in probs))

    def test_title_drift_is_not_a_problem(self):
        self.assertEqual(mz.badge_problems(doc(badge(title="Old name")), [row()]), [])

    def test_wrong_top_level_fails(self):
        self.assertEqual(len(mz.badge_problems([badge()], [row()])), 1)


class ApplyBadges(unittest.TestCase):
    def write(self, text):
        d = tempfile.mkdtemp()
        p = Path(d) / "badges.json"
        p.write_bytes(text)
        return p

    def test_stamps_hv_and_returns_lf_bytes(self):
        p = self.write(json.dumps(doc(badge()), indent=2).replace("\n", "\r\n").encode())
        data = [row(), row(k="other", core="x", sn="x")]
        raw = mz._apply_badges(data, p)
        self.assertNotIn(b"\r\n", raw)
        self.assertEqual(data[0]["hv"], {"reason": "Built from the original schematics.",
                                         "links": ["https://example.org/gng"], "granted": "2026-10-07"})
        self.assertNotIn("hv", data[1])

    def test_problem_stops_the_export(self):
        p = self.write(json.dumps(doc(badge(k="gone"))).encode())
        with self.assertRaises(SystemExit):
            mz._apply_badges([row()], p)

    def test_unreadable_file_stops_the_export(self):
        p = self.write(b"{not json")
        with self.assertRaises(SystemExit):
            mz._apply_badges([row()], p)

    def test_missing_file_is_a_no_op(self):
        self.assertIsNone(mz._apply_badges([row()], Path(tempfile.mkdtemp()) / "none.json"))


class ShippedFile(unittest.TestCase):
    """The committed data/badges.json is well formed (row matching is
    export-web's job, against the rows it is about to publish)."""
    def test_committed_file_parses_and_has_a_header(self):
        d = json.loads(mz.BADGES_JSON.read_text(encoding="utf-8"))
        for key in ("version", "name", "description", "license", "criteria", "badges"):
            self.assertIn(key, d)
        rows = [{"k": b["k"], "base": "Arcade",
                 "core": (b["rbfs"] or [None])[0], "sn": (b["setnames"] or [None])[0]}
                for b in d["badges"]]
        self.assertEqual(mz.badge_problems(d, rows), [])


if __name__ == "__main__":
    unittest.main()
