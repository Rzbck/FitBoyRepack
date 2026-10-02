#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from export_public_metadata import export_snapshot
import publish_public_metadata as publisher

ROOT = Path(__file__).resolve().parents[1]


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE jobs (
          game_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          active INTEGER NOT NULL
        );
        CREATE TABLE results (
          game_id TEXT PRIMARY KEY,
          canonical_title TEXT,
          release_date TEXT,
          genres_json TEXT NOT NULL,
          developer TEXT,
          publisher TEXT,
          platforms_json TEXT NOT NULL,
          confidence REAL NOT NULL,
          evidence_json TEXT NOT NULL,
          checked_at TEXT NOT NULL
        );
        """
    )

    rows = [
        ("alpha", "done", 1, "Alpha Prime", "2024-01-02", '["Action","Adventure"]', "Studio A", "Publisher A", '["Windows","PlayStation 5"]', 0.97, '["https://www.wikidata.org/wiki/Q123"]'),
        ("beta", "review", 1, "Beta", "2022-03-04", '["Puzzle"]', "Studio B", "Publisher B", '["Windows"]', 0.99, '["https://www.wikidata.org/wiki/Q456"]'),
        ("gamma", "done", 1, "Gamma", "2021-05-06", '["RPG"]', "Studio C", "Publisher C", '["Windows"]', 0.85, '["https://www.wikidata.org/wiki/Q789"]'),
        ("delta", "done", 1, "Delta", "2020-07-08", '[]', "Studio D", "Publisher D", '["Windows"]', 0.99, '["https://www.wikidata.org/wiki/Q999"]'),
    ]
    for row in rows:
        game_id, status, active, canonical, release, genres, developer, publisher, platforms, confidence, evidence = row
        conn.execute("INSERT INTO jobs(game_id,status,active) VALUES(?,?,?)", (game_id, status, active))
        conn.execute(
            """
            INSERT INTO results(
              game_id,canonical_title,release_date,genres_json,developer,publisher,
              platforms_json,confidence,evidence_json,checked_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                canonical,
                release,
                genres,
                developer,
                publisher,
                platforms,
                confidence,
                evidence,
                "2026-10-02T12:00:00+00:00",
            ),
        )
    conn.commit()
    conn.close()


def make_source(path: Path) -> None:
    payload = {
        "catalog_version": 1,
        "generated_at": "2026-10-02T12:00:00+00:00",
        "games": [
            {
                "id": "alpha",
                "title": "Alpha Repack",
                "source_url": "https://example.invalid/alpha",
                "post_date": "2026-09-30",
                "genres": ["Shooter"],
                "repack_size": "10 GB",
                "details_version": 1,
                "media_version": 7,
                "details": {},
                "media": [],
            },
            {
                "id": "beta",
                "title": "Beta",
                "source_url": "https://example.invalid/beta",
                "post_date": "2026-09-29",
                "genres": ["Puzzle"],
                "details_version": 1,
                "media_version": 7,
                "details": {},
                "media": [],
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        db = temp / "catalog.sqlite3"
        snapshot = temp / "site" / "data" / "metadata-enrichment.json"
        source = temp / "site" / "data" / "games.json"
        site_root = temp / "site"

        make_db(db)
        make_source(source)

        stats = export_snapshot(db, snapshot, 0.90)
        assert stats["exported"] == 1
        assert stats["skipped_incomplete"] == 1

        public = json.loads(snapshot.read_text(encoding="utf-8"))
        assert public["count"] == 1
        assert set(public["games"]) == {"alpha"}
        alpha = public["games"]["alpha"]
        assert alpha["canonical_title"] == "Alpha Prime"
        assert alpha["wikidata_id"] == "Q123"
        assert "raw_json" not in alpha and "notes" not in alpha and "description_fr" not in alpha

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "build_site_data.py"),
                "--source",
                str(source),
                "--site-root",
                str(site_root),
                "--metadata",
                str(snapshot),
            ],
            cwd=ROOT,
            check=True,
        )

        catalog = json.loads((site_root / "data" / "catalog.json").read_text(encoding="utf-8"))
        health = json.loads((site_root / "data" / "health.json").read_text(encoding="utf-8"))
        search = json.loads((site_root / "data" / "search-index.json").read_text(encoding="utf-8"))

        first = catalog["games"][0]
        assert first["id"] == "alpha"
        assert first["metadata_ready"] is True
        assert first["game_release_date"] == "2024-01-02"
        assert catalog["games"][1]["metadata_ready"] is False

        detail_path = site_root / first["detail_path"]
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        assert detail["verified_metadata"]["developer"] == "Studio A"
        assert detail["title"] == "Alpha Repack"

        assert health["metadata_verified"] == 1
        assert health["coverage"]["metadata"] == 50.0
        assert health["metadata_unmatched"] == 0
        assert 0 in search["prefixes"]["prime"]

        # A fresh export changes generated_at every run. The publisher must not
        # create a Git commit / Pages deployment when metadata itself is identical.
        remote_payload = dict(public)
        remote_payload["generated_at"] = "2026-10-02T12:00:00+00:00"
        remote_bytes = (json.dumps(remote_payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

        original_remote = publisher._remote_content
        original_request = publisher._request_json
        writes = []
        try:
            publisher._remote_content = lambda *_args, **_kwargs: ("remote-sha", remote_bytes)
            publisher._request_json = lambda *_args, **_kwargs: writes.append((_args, _kwargs)) or {}
            publish_stats = publisher.publish_snapshot(
                snapshot,
                repository="Rzbck/FitBoyRepack",
                path="site/data/metadata-enrichment.json",
                branch="main",
                token="test-token",
            )
        finally:
            publisher._remote_content = original_remote
            publisher._request_json = original_request

        assert publish_stats["changed"] is False
        assert writes == []

    print("public metadata export + front merge + idempotent publish OK")


if __name__ == "__main__":
    main()
