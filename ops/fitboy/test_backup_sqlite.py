#!/usr/bin/env python3
"""Backup regression tests with an active WAL source and isolated temp files."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from backup_sqlite import backup, digest, SOURCES


class BackupTests(unittest.TestCase):
    def test_online_snapshot_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            srcs = []
            for relative in SOURCES.values():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                db = sqlite3.connect(path)
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE games (id INTEGER PRIMARY KEY)")
                db.execute("INSERT INTO games VALUES (1)")
                db.commit()
                srcs.append(db)
            try:
                output = backup(root, root / "backups", 14)
                manifest = json.loads((output / "manifest.json").read_text())
                self.assertEqual(set(manifest["databases"]), set(SOURCES))
                for name, stats in manifest["databases"].items():
                    snapshot = output / name
                    self.assertEqual(digest(snapshot), stats["sha256"])
                    self.assertEqual(stats["tables"], {"games": 1})
                    dst = sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True)
                    try:
                        self.assertEqual(dst.execute("PRAGMA quick_check").fetchall(), [("ok",)])
                        self.assertEqual(dst.execute("SELECT id FROM games").fetchall(), [(1,)])
                    finally:
                        dst.close()
                self.assertEqual(srcs[0].execute("SELECT id FROM games").fetchall(), [(1,)])
                self.assertEqual(list((root / "backups").glob(".staging-*")), [])
            finally:
                for db in srcs:
                    db.close()

    def test_partial_failure_never_publishes_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / SOURCES["catalog_enrichment.sqlite3"]
            source.parent.mkdir()
            db = sqlite3.connect(source)
            db.execute("CREATE TABLE test (id INT)")
            db.commit()
            db.close()
            dest = root / "backups"
            with self.assertRaises(FileNotFoundError):
                backup(root, dest, 14)
            self.assertEqual([p.name for p in dest.iterdir()], [".backup.lock"])


if __name__ == "__main__":
    unittest.main()
