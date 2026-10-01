#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

import fast_metadata_bootstrap as fast
from ai_catalog_bootstrap import connect_db, initialize_queue, queue_counts


def game(game_id: str, title: str) -> dict:
    return {
        "id": game_id,
        "title": title,
        "source_url": f"https://example.invalid/{game_id}",
        "post_date": "2026-01-01",
        "genres": [],
        "details": {"description": "Source description."},
    }


def candidate(label: str, qid: str = "Q1") -> dict:
    return {
        "source": "wikidata",
        "url": f"https://www.wikidata.org/wiki/{qid}",
        "id": qid,
        "label": label,
        "description": "video game",
        "instance_of": [fast.VIDEO_GAME_QID],
        "release_dates": ["2025-01-02"],
        "genres": ["adventure game"],
        "developers": ["Studio"],
        "publishers": ["Publisher"],
        "platforms": ["Microsoft Windows"],
    }


def main() -> None:
    assert fast.clean_fast_title("007 First Light – v1.1.0 (Denuvoless)") == "007 First Light"
    assert fast.clean_fast_title("10 Dead Doves, v1.13.3 + Bonus Soundtrack") == "10 Dead Doves"

    picked, score, reason = fast.choose_candidate("Example Game", [candidate("Example Game")])
    assert picked is not None and score >= 0.90 and reason == "accepted"

    picked, _, _ = fast.choose_candidate(
        "Example Game",
        [{"label": "Example Game", "description": "album", "instance_of": [], "release_dates": [], "genres": []}],
    )
    assert picked is None

    assert fast._retry_after_seconds("7", 0) == 7.0
    assert fast._retry_after_seconds(None, 0) >= 5.0

    original_fetch = fast.fetch_one

    def fake_fetch(game_id: str, title: str, candidate_limit: int, request_interval: float):
        del candidate_limit, request_interval
        if game_id == "1":
            return game_id, title, [candidate(title, "Q1")], None
        if game_id == "2":
            return game_id, title, [], None
        if game_id == "3":
            return game_id, title, None, "permanent malformed response"
        return game_id, title, None, "transient: HTTP 429 after retries; retry_after=5.0s"

    fast.fetch_one = fake_fetch
    try:
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "fast.sqlite3"
            conn = connect_db(db)
            games = [
                game("1", "Example Game"),
                game("2", "Unknown Indie"),
                game("3", "Permanent Error Game"),
                game("4", "Rate Limited Game"),
            ]
            initialize_queue(conn, games)
            stats = fast.run_fast_batch(
                conn,
                limit=4,
                workers=2,
                candidate_limit=3,
                threshold=0.90,
                margin=0.08,
                request_interval=0.0,
            )
            assert stats == {
                "processed": 4,
                "done": 1,
                "review": 1,
                "failed": 1,
                "deferred": 1,
                "cache_hits": 0,
            }
            counts = queue_counts(conn)
            assert counts["done"] == 1
            assert counts["review"] == 1
            assert counts["failed"] == 1
            assert counts["pending"] == 1
            transient = conn.execute(
                "SELECT status,last_error FROM jobs WHERE game_id='4'"
            ).fetchone()
            assert transient["status"] == "pending" and "429" in transient["last_error"]

            row = conn.execute(
                "SELECT canonical_title,release_date,description_fr,notes FROM results WHERE game_id='1'"
            ).fetchone()
            assert row["canonical_title"] == "Example Game"
            assert row["release_date"] == "2025-01-02"
            assert row["description_fr"] is None
            assert "French description pending" in row["notes"]

            conn.execute(
                "UPDATE jobs SET status='pending',last_error=NULL,queued_at='1970-01-01T00:00:00+00:00' WHERE game_id='1'"
            )
            conn.commit()

            def should_not_fetch(*_args):
                raise AssertionError("cache miss for known title")

            fast.fetch_one = should_not_fetch
            cached = fast.run_fast_batch(
                conn,
                limit=1,
                workers=1,
                candidate_limit=3,
                threshold=0.90,
                margin=0.08,
                request_interval=0.0,
            )
            assert cached["done"] == 1 and cached["cache_hits"] == 1
            conn.close()
    finally:
        fast.fetch_one = original_fetch

    print("fast metadata bootstrap OK")


if __name__ == "__main__":
    main()
