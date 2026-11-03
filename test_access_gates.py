"""Missing upstream access labels must not announce supporter-only games."""
import argparse
import hashlib
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import misterzine as mz


KEYED = b'<misterromdescription><rom index="37" zip="coinopkey.zip"><part name="coinop.key"/></rom></misterromdescription>'
PUBLIC = b'<misterromdescription><rom zip="game.zip"/></misterromdescription>'
PATH = "_Arcade/Test Game [CoC].mra"
BETA = "coinop-collection-beta"
ALPHA = "coinop-collection-alpha"


class AccessGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, value in {"DATA": self.root, "DBPATH": self.root / "test.sqlite",
                            "CACHEDIR": self.root / "cache", "SNAPDIR": self.root / "snapshots"}.items():
            patcher = mock.patch.object(mz, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.source = {"id": "coinop", "name": "Coin-Op", "db_url": "https://example.test/db.json"}
        self.db = {"timestamp": 1793499110, "base_files_url": "https://example.test/pinned/",
                   "default_options": {"filter": "[MiSTer] !coinop-collection-beta !coinop-collection-alpha"},
                   "tag_dictionary": {"coinopcollectionbeta": 1, "coinopcollectionalpha": 2}, "files": {}}
        self.payloads = {}
        self.add_mra(PATH, KEYED)
        patcher = mock.patch.object(mz, "http_get", side_effect=self.download)
        self.http = patcher.start()
        self.addCleanup(patcher.stop)

    def add_mra(self, path, raw, tags=(), url=None):
        meta = {"hash": hashlib.md5(raw).hexdigest(), "size": len(raw), "tags": list(tags)}
        if url:
            meta["url"] = url
        self.db["files"][path] = meta
        self.payloads[url or self.db["base_files_url"] + mz.urllib.parse.quote(path, safe="/")] = raw

    def download(self, url, **kwargs):
        return json.dumps(self.db).encode() if url == self.source["db_url"] else self.payloads[url]

    def fetch(self):
        return mz.fetch_db(self.source)[2]

    def snapshot(self):
        with mock.patch.object(mz, "SOURCES", [self.source]):
            mz.cmd_snapshot(argparse.Namespace(source="coinop"))

    def test_untagged_key_is_gated_and_warm_cache_needs_only_database(self):
        self.assertEqual(self.fetch(), {PATH: BETA})
        self.http.reset_mock()
        self.assertEqual(self.fetch(), {PATH: BETA})
        self.http.assert_called_once_with(self.source["db_url"])

    def test_explicit_alpha_and_beta_tags_keep_their_stage_without_download(self):
        self.add_mra(PATH, KEYED, tags=[2])
        self.add_mra("_Arcade/Beta.mra", PUBLIC, tags=[1])
        self.assertEqual(self.fetch(), {PATH: ALPHA, "_Arcade/Beta.mra": BETA})
        self.http.assert_called_once_with(self.source["db_url"])

    def test_comments_and_other_keys_are_public_but_active_key_in_zip_list_is_gated(self):
        self.add_mra(PATH, b'<misterromdescription><!-- <rom zip="coinopkey.zip"/> -->'
                     b'<rom zip="jtbeta.zip"/><description>coinopkey.zip</description></misterromdescription>')
        self.add_mra("_Arcade/Other.mra", b"<misterromdescription><rom zip='game.zip | COINOPKEY.ZIP'/></misterromdescription>")
        self.assertEqual(self.fetch(), {"_Arcade/Other.mra": BETA})

    def test_per_file_url_is_used_and_changed_hash_rechecks_negative_cache(self):
        self.add_mra(PATH, PUBLIC, url="https://example.test/override")
        self.assertEqual(self.fetch(), {})
        self.add_mra(PATH, KEYED, url="https://example.test/new-version")
        self.assertEqual(self.fetch(), {PATH: BETA})
        self.assertIn(mock.call("https://example.test/new-version"), self.http.call_args_list)

    def test_other_sources_are_not_inferred_to_be_coinop_betas(self):
        self.source["id"] = "jtbindb"
        self.assertEqual(self.fetch(), {})
        self.http.assert_called_once_with(self.source["db_url"])

    def test_correction_retracts_only_events_for_the_same_keyed_revision_and_source(self):
        con = mz.connect()
        digest = self.db["files"][PATH]["hash"]
        for sid, revision in [("coinop", digest), ("coinop", "older-public"), ("jtbindb", digest)]:
            con.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                        ("2026-11-01T10:00:00+00:00", sid, PATH, "Test Game", "arcade", "new", revision))
        con.commit()
        con.close()
        self.snapshot()
        con = mz.connect()
        remaining = {tuple(r) for r in con.execute("SELECT source_id,hash FROM events")}
        self.assertEqual(remaining, {("coinop", "older-public"), ("jtbindb", digest)})
        con.close()

    def test_failures_do_not_replace_cache_or_graduate_existing_beta(self):
        self.snapshot()
        before = (mz.CACHEDIR / "coinop_access.json").read_bytes()
        self.add_mra(PATH, PUBLIC)
        url = self.db["base_files_url"] + mz.urllib.parse.quote(PATH, safe="/")
        for failed in [KEYED, None, b"<broken"]:
            with self.subTest(failed=failed):
                if failed == b"<broken":
                    self.add_mra(PATH, failed)
                elif failed is None:
                    self.payloads.pop(url)
                else:
                    self.payloads[url] = failed
                with self.assertRaises((ValueError, KeyError)):
                    self.snapshot()
                self.assertEqual((mz.CACHEDIR / "coinop_access.json").read_bytes(), before)
                con = mz.connect()
                self.assertEqual(con.execute("SELECT beta FROM catalog WHERE path=?", (PATH,)).fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT count(*) FROM events").fetchone()[0], 0)
                con.close()

    def test_new_beta_stays_quiet_then_key_removal_announces_public_release_once(self):
        # An existing public game makes this a normal diff, not first-time seeding.
        self.db["files"].clear()
        self.add_mra("_Arcade/Existing.mra", PUBLIC)
        # Keep another known beta so the existing mass-graduation tripwire
        # does not require an operator override when our test game graduates.
        self.add_mra("_Arcade/Tagged.mra", KEYED, tags=[1])
        self.snapshot()
        self.db["timestamp"] += 86400
        self.add_mra(PATH, KEYED)
        self.snapshot()
        self.snapshot()
        con = mz.connect()
        row = con.execute("SELECT * FROM catalog WHERE path=?", (PATH,)).fetchone()
        debut = row["release_date"]
        self.assertEqual((row["beta"], row["gate"]), (1, BETA))
        self.assertEqual(con.execute("SELECT count(*) FROM events").fetchone()[0], 0)
        con.close()
        self.add_mra(PATH, PUBLIC)
        self.db["timestamp"] += 86400
        self.snapshot()
        self.snapshot()
        con = mz.connect()
        row = con.execute("SELECT * FROM catalog WHERE path=?", (PATH,)).fetchone()
        self.assertEqual((row["beta"], row["release_date"]), (0, debut))
        events = [tuple(r) for r in con.execute("SELECT path,event_type FROM events")]
        self.assertEqual(events, [(PATH, "new")])
        con.close()

    def test_corrected_beta_is_excluded_from_old_feed_events_without_hiding_public_version(self):
        con = mz.connect()
        for sid in ["coinop", "jtbindb"]:
            con.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                        ("2026-11-01T10:00:00+00:00", sid, PATH, "Test Game", "arcade", "new", "hash"))
        con.commit()
        con.close()
        rows = [{"title": "Test Game", "base": "Arcade", "src": sid, "mra": PATH,
                 "k": sid, "beta": sid == "coinop"} for sid in ["coinop", "jtbindb"]]
        (self.root / "data.json").write_text(json.dumps(rows), encoding="utf-8")
        mz._write_feeds(self.root)
        for feed in ["feed.xml", "feed-new.xml"]:
            items = ET.parse(self.root / feed).findall(".//item")
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0].findtext("guid").startswith("jtbindb:"))


class GatedTitleTests(unittest.TestCase):
    def row(self, title, sn, beta=False, source=None):
        return {"title": title, "setname": sn, "beta": beta, "system": "arcade",
                "source_id": source or ("coinop" if beta else "jtbindb"),
                "path": f"_Arcade/{title}.mra", "rbf": "beta_core" if beta else "public_core",
                "repo": ""}

    def label(self, rows, titles, meta):
        chosen = {(r["source_id"], r["path"]): (t, None) for r, t in zip(rows, titles)}
        mz._label_gated_arcade_titles(rows, chosen, meta, {}, {})
        # Exercise the later title cleanup too: it must retain the source label.
        data = []
        for r in rows:
            title, alias = chosen[(r["source_id"], r["path"])]
            data.append({"title": title, "mt": alias, "sn": r["setname"],
                         "src": r["source_id"], "base": "Arcade", "beta": r["beta"]})
        mz._humanize_arcade_titles(data, meta)
        return data

    def test_same_set_labels_beta_despite_punctuation_or_retained_filename(self):
        for public, beta, sn, desc, beta_display in [
            ("1941 Counter Attack", "1941 - Counter Attack (World 900227) [CoC]", "1941",
             "1941: Counter Attack (World 900227)", "1941 - Counter Attack"),
            ("Willow", "Willow (World) [CoC]", "willow", "Willow (World)", "Willow (World) [CoC]"),
        ]:
            with self.subTest(sn=sn):
                rows = [self.row(public, sn), self.row(beta, sn, beta=True)]
                data = self.label(rows, [public, beta_display], {sn: {"desc": desc}})
                base = mz._strip_trailing_parens(desc)
                self.assertEqual(data[0]["title"], base)
                self.assertEqual(data[1]["title"], base + " (Coin-Op Collection)")
                self.assertEqual(data[1]["mt"], beta)

    def test_clone_matches_same_name_ignoring_punctuation(self):
        rows = [self.row("Game: Subtitle (World)", "game"),
                self.row("Game - Subtitle (Japan) [CoC]", "gamej", beta=True)]
        meta = {"game": {"desc": "Game: Subtitle (World)"},
                "gamej": {"parent": "game", "desc": "Game: Subtitle (Japan)"}}
        data = self.label(rows, ["Game: Subtitle", "Game - Subtitle"], meta)
        self.assertEqual(data[1]["title"], "Game: Subtitle (Coin-Op Collection)")

    def test_shared_family_or_core_alone_does_not_label_another_game(self):
        rows = [self.row("Sprint 2", "sprint2"),
                self.row("Sprint 1", "sprint1", beta=True),
                self.row("Unrelated", "other", beta=True)]
        meta = {"sprint1": {"parent": "sprint2"}}
        data = self.label(rows, [r["title"] for r in rows], meta)
        self.assertEqual([d["title"] for d in data], [r["title"] for r in rows])

    def test_existing_exact_title_fallback_without_set_metadata(self):
        rows = [self.row("Black Heart", ""), self.row("Black Heart", "", beta=True)]
        data = self.label(rows, [r["title"] for r in rows], {})
        self.assertEqual([d["title"] for d in data],
                         ["Black Heart", "Black Heart (Coin-Op Collection)"])

    def test_public_titles_stay_stable_and_other_sources_get_their_own_label(self):
        rows = [self.row("Game", "game", source="coinop"),
                self.row("Game [JT]", "game", beta=True, source="jtbindb")]
        data = self.label(rows, ["Game", "Game [JT]"], {"game": {"desc": "Game"}})
        alone = self.label(rows[:1], ["Game"], {"game": {"desc": "Game"}})
        self.assertEqual(data[0], alone[0])
        self.assertEqual(data[1]["title"], "Game (Jotego)")


if __name__ == "__main__":
    unittest.main()
