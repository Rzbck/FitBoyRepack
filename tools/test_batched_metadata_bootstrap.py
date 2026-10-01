#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

import batched_metadata_bootstrap as batched
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


def qclaim(qid: str) -> dict:
    return {"mainsnak": {"datavalue": {"value": {"id": qid}}}}


def tclaim(date: str) -> dict:
    return {"mainsnak": {"datavalue": {"value": {"time": f"+{date}T00:00:00Z"}}}}


def candidate_entity(label: str) -> dict:
    return {
        "labels": {"en": {"value": label}},
        "descriptions": {"en": {"value": "video game"}},
        "claims": {
            "P31": [qclaim(batched.VIDEO_GAME_QID)],
            "P577": [tclaim("2025-01-02")],
            "P136": [qclaim("QGENRE")],
            "P178": [qclaim("QDEV")],
            "P123": [qclaim("QPUB")],
            "P400": [qclaim("QPLATFORM")],
        },
    }


class FakeClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def search(self, title: str, limit: int):
        if title == "Example Game":
            return ["Q1"][:limit]
        return []

    def entities(self, ids: list[str], props: str):
        out = {}
        for qid in ids:
            if qid == "Q1":
                out[qid] = candidate_entity("Example Game")
            elif qid == "QGENRE":
                out[qid] = {"labels": {"en": {"value": "Adventure game"}}}
            elif qid == "QDEV":
                out[qid] = {"labels": {"en": {"value": "Studio"}}}
            elif qid == "QPUB":
                out[qid] = {"labels": {"en": {"value": "Publisher"}}}
            elif qid == "QPLATFORM":
                out[qid] = {"labels": {"en": {"value": "Microsoft Windows"}}}
        return out


class TransientClient(FakeClient):
    def search(self, title: str, limit: int):
        raise batched.TransientStop("HTTP 429 retry_after=60")


def main() -> None:
    original = batched.BatchWikidataClient
    try:
        batched.BatchWikidataClient = FakeClient
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "batched.sqlite3"
            conn = connect_db(db)
            initialize_queue(conn, [game("1", "Example Game"), game("2", "Unknown Indie")])

            stats = batched.run_batched(
                conn,
                limit=2,
                candidate_limit=3,
                request_interval=0.0,
                maxlag=10,
                threshold=0.90,
                margin=0.08,
            )
            assert stats["done"] == 1
            assert stats["review"] == 1
            assert stats["deferred"] == 0
            assert stats["search_requests"] == 2
            assert stats["entity_requests"] == 2
            counts = queue_counts(conn)
            assert counts["done"] == 1 and counts["review"] == 1

            row = conn.execute(
                "SELECT canonical_title,release_date,developer,publisher FROM results WHERE game_id='1'"
            ).fetchone()
            assert row["canonical_title"] == "Example Game"
            assert row["release_date"] == "2025-01-02"
            assert row["developer"] == "Studio"
            assert row["publisher"] == "Publisher"
            conn.close()

        batched.BatchWikidataClient = TransientClient
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "transient.sqlite3"
            conn = connect_db(db)
            initialize_queue(conn, [game("3", "Rate Limited Game")])
            stats = batched.run_batched(
                conn,
                limit=1,
                candidate_limit=3,
                request_interval=0.0,
                maxlag=10,
                threshold=0.90,
                margin=0.08,
            )
            assert stats["deferred"] == 1
            assert stats["failed"] == 0
            row = conn.execute("SELECT status,last_error FROM jobs WHERE game_id='3'").fetchone()
            assert row["status"] == "pending"
            assert "429" in row["last_error"]
            conn.close()
    finally:
        batched.BatchWikidataClient = original

    print("batched metadata bootstrap OK")


if __name__ == "__main__":
    main()
