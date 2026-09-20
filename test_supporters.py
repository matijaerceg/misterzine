"""The supporter credits merge: who is current, who is past, and what the
public file shows."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
import patreon_supporters as ps  # noqa: E402


def member(mid, name, status, start="2026-09-19T21:25:40.999+00:00"):
    return {"id": mid, "type": "member",
            "attributes": {"full_name": name, "patron_status": status, "pledge_relationship_start": start}}


class Merge(unittest.TestCase):
    def test_new_active_patron_is_current_with_start_month(self):
        src, changes = ps.merge({"members": {}}, [member("1", "Malento", "active_patron")], "2026-10")
        self.assertEqual(src["members"]["1"]["since"], "2026-09")
        self.assertIsNone(src["members"]["1"]["until"])
        self.assertEqual(changes, ["current (new): Malento"])

    def test_free_followers_are_ignored(self):
        src, changes = ps.merge({"members": {}}, [member("2", "Someone", None, None)], "2026-10")
        self.assertEqual(src["members"], {})
        self.assertEqual(changes, [])

    def test_former_patron_moves_to_past_and_stays(self):
        src, _ = ps.merge({"members": {}}, [member("1", "Malento", "active_patron")], "2026-09")
        src, changes = ps.merge(src, [member("1", "Malento", "former_patron")], "2026-11")
        self.assertEqual(src["members"]["1"]["until"], "2026-11")
        self.assertEqual(changes, ["past: Malento"])
        src, changes = ps.merge(src, [member("1", "Malento", "former_patron")], "2026-12")
        self.assertEqual(src["members"]["1"]["until"], "2026-11", "the end month is not pushed along")
        self.assertEqual(changes, [])

    def test_gone_from_patreon_moves_to_past(self):
        src, _ = ps.merge({"members": {}}, [member("1", "Malento", "active_patron")], "2026-09")
        src, changes = ps.merge(src, [], "2026-11")
        self.assertEqual(src["members"]["1"]["until"], "2026-11")
        self.assertEqual(changes, ["past (gone from Patreon): Malento"])

    def test_declined_card_stays_current(self):
        src, _ = ps.merge({"members": {}}, [member("1", "Malento", "active_patron")], "2026-09")
        src, changes = ps.merge(src, [member("1", "Malento", "declined_patron")], "2026-11")
        self.assertIsNone(src["members"]["1"]["until"])
        self.assertEqual(changes, [])

    def test_returning_supporter_keeps_original_start(self):
        src, _ = ps.merge({"members": {}}, [member("1", "Malento", "active_patron")], "2026-09")
        src, _ = ps.merge(src, [member("1", "Malento", "former_patron")], "2026-11")
        src, changes = ps.merge(src, [member("1", "Malento", "active_patron", "2027-02-01T00:00:00+00:00")], "2027-02")
        self.assertEqual(src["members"]["1"]["since"], "2026-09")
        self.assertIsNone(src["members"]["1"]["until"])
        self.assertEqual(changes, ["current (returned): Malento"])

    def test_hand_edited_name_sticks_and_patreon_name_follows(self):
        src, _ = ps.merge({"members": {}}, [member("1", "Marco Puszina", "active_patron")], "2026-09")
        src["members"]["1"]["name"] = "dh3lix-pooch"
        src, _ = ps.merge(src, [member("1", "Marco P.", "active_patron")], "2026-10")
        self.assertEqual(src["members"]["1"]["name"], "dh3lix-pooch")
        self.assertEqual(src["members"]["1"]["patreon_name"], "Marco P.")

    def test_already_ended_newcomer_lands_in_past(self):
        src, changes = ps.merge({"members": {}}, [member("3", "Old", "former_patron")], "2026-10")
        self.assertEqual(src["members"]["3"]["until"], "2026-10")
        self.assertEqual(changes, ["past (new record, already ended): Old"])


class Public(unittest.TestCase):
    def test_public_file_sorts_and_hides(self):
        src = {"members": {
            "1": {"name": "zed", "since": "2026-09", "until": None},
            "2": {"name": "Anna", "since": "2026-08", "until": None},
            "3": {"name": "Gone", "since": "2026-05", "until": "2026-07"},
            "4": {"name": "Secret", "since": "2026-05", "until": None, "hidden": True},
        }}
        pub = ps.public_view(src, "2026-10-01")
        self.assertEqual(pub["updated"], "2026-10-01")
        self.assertEqual([c["name"] for c in pub["current"]], ["Anna", "zed"])
        self.assertEqual(pub["past"], [{"name": "Gone", "since": "2026-05", "until": "2026-07"}])
        self.assertNotIn("patreon_name", pub["current"][0])


if __name__ == "__main__":
    unittest.main()
