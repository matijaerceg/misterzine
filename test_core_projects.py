import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core_projects as cp
import misterzine as mz


WIKI = b"""<!-- cores_list_start -->
| [Console](https://github.com/MiSTer-devel/Console_MiSTer) |
<!-- cores_list_end -->
<!-- arcade_list_start -->
| [Different Name](https://github.com/MiSTer-devel/Console_MiSTer/tree/Board ) |
| [Second](https://github.com/MiSTer-devel/Arcade-Second_MiSTer) |
<!-- arcade_list_end -->"""
FILE = "_Arcade/cores/S32_20261105.rbf"
ROM = {"name": "S32_20261105.rbf", "type": "blob", "oid": "exact"}
SOURCE = "https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/" + "a" * 40


class OfficialProjectsTests(unittest.TestCase):
    def test_exact_build_branch_cache_retry_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "official.json"
            db = {"base_files_url": SOURCE, "files": {FILE: {"hash": "md5"}}}
            second = dict(ROM, oid="different")
            def trees(requests):
                result = []
                for repo, ref, path in requests:
                    if repo == cp.DIST:
                        self.assertEqual((ref, path), ("a" * 40, "_Arcade/cores"))
                    file = second if repo.endswith("Second_MiSTer") else ROM
                    result.append(("main", [file]))
                return result
            # The same blob in a console project cannot claim an arcade release.
            cp.refresh_official(db, cache, lambda _: WIKI, lambda _: None, trees)
            match = json.loads(cache.read_text())["files"][FILE]
            self.assertEqual(match, ["md5", ["MiSTer-devel/Console_MiSTer/tree/Board"]])
            cp.refresh_official(db, cache, lambda _: WIKI, read_trees=lambda _: self.fail("warm lookup"))

            # A new snapshot needs new proof. An outage preserves the previous cache;
            # the exporter also checks its digest before applying it to any build.
            original = cache.read_bytes()
            db["files"][FILE]["hash"] = "md5-new"
            def unavailable(_):
                raise RuntimeError("upstream unavailable")
            with self.assertRaises(RuntimeError):
                cp.refresh_official(db, cache, lambda _: WIKI, read_trees=unavailable)
            self.assertEqual(cache.read_bytes(), original)
            second["oid"] = "exact"
            logs = []
            cp.refresh_official(db, cache, lambda _: WIKI, logs.append, trees)
            cp.refresh_official(db, cache, lambda _: WIKI, logs.append, trees)
            self.assertEqual(sum("::warning::" in line for line in logs), 1)
            self.assertEqual(len(json.loads(cache.read_text())["files"][FILE][1]), 2)
            second["oid"] = "different"
            cp.refresh_official(db, cache, lambda _: WIKI, logs.append, trees)
            self.assertEqual(json.loads(cache.read_text())["files"][FILE][1], match[1])


class CatalogueProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        patcher = patch.object(mz, "CACHEDIR", self.cache)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.con = sqlite3.connect(":memory:")
        self.addCleanup(self.con.close)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(mz.SCHEMA)
        mz._ensure_columns(self.con)

    def test_source_filename_hash_and_url_only_changes(self):
        def row(sid, tag):
            return {"source_id": sid, "path": "_Arcade/game.mra", "rbf": tag, "repo": "", "system": "arcade"}
        official = row("distribution_mister", "S32")
        community = row("ppriest", "S32")
        rows = [official, community]
        def lookup():
            return mz.verified_project_links(self.con, rows, mz._shipped_rbf_index(self.con))
        def record(sid, repo):
            return mz.upsert_core_files(self.con, sid, {FILE: {"hash": "digest", "download_repo": repo}}, "now")
        def cache(digest, projects):
            (self.cache / "official_core_projects.json").write_text(json.dumps({"files": {FILE: [digest, projects]}}))
        record("distribution_mister", None)
        url = "https://raw.githubusercontent.com/ppriest/Specific/abc123/releases/Arcade-S32.rbf"
        record("ppriest", mz.core_download_repo(url))
        oid = ("distribution_mister", official["path"])
        cid = ("ppriest", community["path"])
        cache("digest", ["MiSTer-devel/Project/tree/Board"])
        self.assertEqual(lookup(), {oid: "MiSTer-devel/Project/tree/Board", cid: "ppriest/Specific"})
        self.assertEqual(record("ppriest", "ppriest/Corrected"), [])
        self.assertEqual(lookup()[cid], "ppriest/Corrected")
        self.assertIsNone(self.con.execute("SELECT changed FROM core_files WHERE source_id='ppriest'").fetchone()[0])
        for repo in ("someone/mirror", "ppriest/MiSTer_ppriest", None):
            record("ppriest", repo)
            self.assertNotIn(cid, lookup())
        cache("old", ["MiSTer-devel/Project"])
        self.assertNotIn(oid, lookup())
        cache("digest", ["MiSTer-devel/A", "MiSTer-devel/B"])
        official["repo"] = "MiSTer-devel/A"
        self.assertEqual(mz._repo_for(official, "S32", {"projects": lookup()}), "")
        self.assertIsNone(mz.core_download_repo("https://example.com/ppriest/Specific/Arcade-S32.rbf"))

    def test_date_pinned_and_undated_launchers_use_their_exact_files(self):
        builds = {name: {"hash": name, "download_repo": f"ppriest/{project}"} for name, project in [
            ("_Arcade/cores/Board.rbf", "Original"),
            ("_Arcade/cores/Board_20261101.rbf", "First"),
            ("_Arcade/cores/Board_20261105.rbf", "Second")]}
        mz.upsert_core_files(self.con, "ppriest", builds, "now")
        rows = [{"source_id": "ppriest", "path": tag + ".mra", "rbf": tag, "system": "arcade", "repo": ""}
                for tag in ("Board", "Board_20261101")]
        links = mz.verified_project_links(self.con, rows, mz._shipped_rbf_index(self.con))
        self.assertEqual(links["ppriest", "Board.mra"], "ppriest/Original")
        self.assertEqual(links["ppriest", "Board_20261101.mra"], "ppriest/First")

    def test_jotego_repairs_foreign_port_without_creating_a_release(self):
        self.con.execute("INSERT INTO jt_cores(folder,rbf,last_commit) VALUES('1942','jt1942','2026-11-03T19:00:00Z')")
        path = "_Arcade/1942 (Revision B).mra"
        self.con.execute("INSERT INTO catalog(source_id,path,system,rbf,release_date,repo,last_update) "
                         "VALUES('jtbindb',?,'arcade','jt1942','2019-02-14','MiSTer-devel/Old','2020-01-08')", (path,))
        self.con.execute("INSERT INTO row_keys(source_id,path,k) VALUES('jtbindb',?,'1942')", (path,))
        self.con.execute("INSERT INTO row_batches VALUES('1942','2020-01-08',1,'2026-09-09')")
        for _ in range(2):
            mz.join_jt_to_catalog(self.con)
            mz.apply_jt_beta_frozen_dates(self.con)
        row = self.con.execute("SELECT repo,release_date,last_update FROM catalog").fetchone()
        self.assertEqual(tuple(row), ("jotego/jtcores (cores/1942)", "2019-02-07", "2026-11-03T19:00:00Z"))
        batch = self.con.execute("SELECT updated,batch,stamped_at FROM row_batches").fetchone()
        self.assertEqual(tuple(batch), ("2026-11-03", 1, row["last_update"]))
        self.assertEqual(self.con.execute("SELECT count(*) FROM events").fetchone()[0], 0)
