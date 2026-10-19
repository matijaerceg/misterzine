"""Arcade genre: the catver subgenre mapping, the set pins and the genre of
every game in the published catalogue's 2026-10-16 cohort, pinned so a catver
drift or a mapping change shows up."""
import json
import unittest
from pathlib import Path

import misterzine as mz

ROOT = Path(__file__).resolve().parent

# test_genre_pins.json: the genre of every arcade row in docs/releases/data.json
# that debuted on or before 2026-10-16, per MAME setname (per title for the few
# rows without one), from data/cache/catver.ini as committed on that date.
# Pinned per game rather than as per-genre totals: the upstream dbs drop,
# rename and re-set games on their own schedule (Meathax's Simpsons left and
# came back as simpsons2p, 2026-10-18/19), and a total that moves with them
# failed the scheduled refresh. A game that has left the catalogue is skipped;
# a game still listed under another genre fails, naming the set: catver moved
# it, or a mapping/pin change did. Re-pin only after checking why.
PINS = json.loads((ROOT / "test_genre_pins.json").read_text(encoding="utf-8"))


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
    def test_pinned_genres(self):
        cats = mz.local_catver()
        dat = mz.load_arcade_dat_meta()
        self.assertTrue(cats and dat, "data/cache/catver.ini and mame_meta.json.gz must be present")
        rows = json.loads((ROOT / "docs/releases/data.json").read_text(encoding="utf-8"))
        moved, seen = [], set()
        for r in rows:
            if r.get("base") != "Arcade":
                continue
            sn = (r.get("sn") or "").lower()
            want = PINS["sets"].get(sn) if sn else PINS["titles"].get(r["title"])
            if want is None:
                continue  # not in the cohort: a later debut, or another db's copy
            seen.add(sn or r["title"])
            got = mz.genre_for(r.get("sn"), cats, dat) or mz.arcade_genre(r.get("sn"), r["title"]) or "(none)"
            if got != want:
                moved.append(f"{sn or r['title']}: pinned {want!r}, now {got!r}")
        self.assertEqual(sorted(set(moved)), [])
        # games leaving the catalogue is fine, but most of the cohort vanishing
        # means data.json or the setname join broke, not upstream churn
        pinned = len(PINS["sets"]) + len(PINS["titles"])
        self.assertGreater(len(seen), pinned * 0.9, f"only {len(seen)} of {pinned} pinned games found")

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
