"""Arcade genre: the catver subgenre mapping, the set pins and the per-genre
counts of the published catalogue, pinned so a catver drift shows up."""
import collections
import json
import unittest
from pathlib import Path

import misterzine as mz

ROOT = Path(__file__).resolve().parent

# Per-genre row counts of docs/releases/data.json's arcade rows that debuted
# on or before PINNED_THROUGH, from data/cache/catver.ini as committed on
# that date. Rows added later are left out so catalogue growth keeps the pin
# valid; a change here means catver moved a set, a pin changed, or a row was
# dropped or retitled. Re-pin only after checking which rows moved and why.
# The historical count is 115 after the Meathax Simpsons row was withdrawn
# upstream (2026-10-12); the older Jotego Simpsons row remains in the data.
PINNED_THROUGH = "2026-10-16"
PINNED_COUNTS = {
    "Shoot 'em up": 261, "Platformer": 161, "Sports": 131, "Beat 'em up": 115,
    "Run 'n gun": 108, "Maze": 92, "Fighting": 88, "Puzzle": 87,
    "Arena shooter": 80, "Fixed shooter": 75, "Racing": 64, "Tabletop & quiz": 41,
    "Other": 27, "Light gun": 25, "Rail shooter": 24,
}


class MappingTests(unittest.TestCase):
    def test_labels(self):
        for value, want in [
            ("Shooter / Flying Vertical", "Shoot 'em up"),
            ("Shooter / Misc.", "Shoot 'em up"),
            ("Shooter / Something New", "Shoot 'em up"),   # unlisted subgenre
            ("Shooter / Walking", "Run 'n gun"),
            ("Platform / Shooter Scrolling", "Run 'n gun"),
            ("Fighter / Versus", "Fighting"),
            ("Fighter / 2.5D", "Beat 'em up"),
            ("Fighter / Something New", "Beat 'em up"),
            ("Platform / Fighter", "Beat 'em up"),
            ("Platform / Fighter Scrolling", "Platformer"),
            ("Platform / Run Jump", "Platformer"),
            ("Climbing / Building", "Platformer"),
            ("Shooter / Field", "Arena shooter"),
            ("Maze / Shooter Small", "Arena shooter"),
            ("Maze / Collect", "Maze"),
            ("Shooter / Gallery", "Fixed shooter"),
            ("Shooter / Gun", "Light gun"),
            ("Shooter / Flying 1st Person", "Rail shooter"),
            ("Driving / Race (chase view)", "Racing"),
            ("Ball & Paddle / Breakout", "Puzzle"),
            ("Puzzle / Drop", "Puzzle"),
            ("Sports / Soccer", "Sports"),
            ("Tabletop / Mahjong", "Tabletop & quiz"),
            ("Quiz / Questions in English", "Tabletop & quiz"),
            ("Gambling / Cards", "Other"),
            ("Pinball", "Other"),
            ("Unknown", "Other"),
            ("TTL * Shooter / Gallery", "Fixed shooter"),
            ("Arcade / Pinball", "Other"),
            ("Puzzle / Outline * Mature *", "Puzzle"),
            ("", ""),
        ]:
            with self.subTest(value=value):
                self.assertEqual(mz.genre_label(value), want)

    def test_every_label_is_a_site_genre(self):
        labels = set(mz.GENRE_BY_SUBGENRE.values()) | set(mz.GENRE_BY_TOP.values())
        labels |= set(mz.GENRE_OVERRIDES.values()) | set(mz.ARCADE_GENRE_BY_SETNAME.values())
        labels |= set(mz.ARCADE_GENRE_BY_NAME.values()) | set(mz.LEGACY_GENRE.values())
        self.assertTrue(labels <= set(mz.GENRES), labels - set(mz.GENRES))

    def test_pins_beat_catver_and_reach_clones(self):
        cats = {"baddudes": "Platformer", "drgninja": "Platformer", "galaga": "Fixed shooter"}
        dat = {"drgninja": {"parent": "baddudes"}, "galagab": {"parent": "galaga"}}
        self.assertEqual(mz.genre_for("baddudes", cats, dat), "Beat 'em up")
        self.assertEqual(mz.genre_for("DRGNINJA", cats, dat), "Beat 'em up")
        self.assertEqual(mz.genre_for("galagab", cats, dat), "Fixed shooter")
        self.assertEqual(mz.genre_for("nosuchset", cats, dat), "")

    def test_export_translates_a_stale_db_label(self):
        from test_card_status import arcade
        row = mz._web_row(arcade(setname="nosuchset", title="No Such Game", genre="Shooter"))
        self.assertEqual(row["genre"], "Shoot 'em up")


class CatalogueTests(unittest.TestCase):
    def test_pinned_counts(self):
        cats = mz.local_catver()
        dat = mz.load_arcade_dat_meta()
        self.assertTrue(cats and dat, "data/cache/catver.ini and mame_meta.json.gz must be present")
        rows = json.loads((ROOT / "docs/releases/data.json").read_text(encoding="utf-8"))
        counts = collections.Counter()
        for r in rows:
            # Ongo was added after this frozen cohort; keep its undated seed
            # rows out without changing the original treatment of legacy rows.
            if r.get("src") == "ongo":
                continue
            if r.get("base") != "Arcade" or (r.get("date") or "")[:10] > PINNED_THROUGH:
                continue
            counts[mz.genre_for(r.get("sn"), cats, dat) or mz.arcade_genre(r.get("sn"), r["title"])
                   or "(none)"] += 1
        self.assertEqual(dict(counts), PINNED_COUNTS)

    def test_pinned_sets_exist_in_the_catalogue(self):
        rows = json.loads((ROOT / "docs/releases/data.json").read_text(encoding="utf-8"))
        dat = mz.load_arcade_dat_meta()
        sets = set()
        for r in rows:
            sn = (r.get("sn") or "").lower()
            if sn:
                sets.add(sn)
                sets.add((dat.get(sn) or {}).get("parent") or sn)
        missing = sorted(set(mz.GENRE_OVERRIDES) - sets)
        self.assertEqual(missing, [], "GENRE_OVERRIDES pins sets the catalogue no longer lists")


if __name__ == "__main__":
    unittest.main()
