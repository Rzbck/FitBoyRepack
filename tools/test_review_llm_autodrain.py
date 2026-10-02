#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import review_llm_autodrain as worker


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, *_args, **_kwargs):
        self.calls += 1
        if not self.responses:
            raise AssertionError("unexpected LLM call")
        value = self.responses.pop(0)
        return json.dumps(value) if isinstance(value, dict) else str(value)


def candidate(qid: str, label: str) -> dict:
    return {
        "source": "wikidata",
        "url": f"https://www.wikidata.org/wiki/{qid}",
        "id": qid,
        "label": label,
        "description": "video game",
        "instance_of": ["Q7889"],
        "release_dates": ["2024-05-01"],
        "genres": ["Adventure game"],
        "developers": ["Example Studio"],
        "publishers": ["Example Publisher"],
        "platforms": ["Microsoft Windows"],
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "catalog.sqlite3"
        conn = worker.base.connect_db(db)
        games = [
            {"id": "g1", "title": "Example Game: Deluxe Edition", "genres": ["Adventure"]},
            {"id": "g2", "title": "No Evidence Game", "genres": []},
            {"id": "g3", "title": "Ambiguous Game", "genres": ["Adventure"]},
        ]
        worker.base.initialize_queue(conn, games)
        worker.base.ensure_cache(conn)
        conn.execute("UPDATE jobs SET status='review'")
        conn.commit()

        c1 = candidate("Q100", "Example Game")
        c3 = candidate("Q300", "Ambiguous Game")
        worker.base.store_cache(conn, games[0]["title"], [c1])
        worker.base.store_cache(conn, games[2]["title"], [c3])
        conn.commit()

        fake = FakeLLM(
            [
                {"candidate_id": "Q100", "confidence": 0.97, "reason": "same base game"},
                {"candidate_id": None, "confidence": 0.55, "reason": "insufficient identity evidence"},
            ]
        )
        stats = worker.run_reviews(
            conn,
            {game["id"]: game for game in games},
            fake,
            limit=10,
            confidence_threshold=0.92,
            max_error_attempts=3,
        )

        assert stats["llm_calls"] == 2, stats
        assert stats["resolved"] == 1, stats
        assert stats["unresolved"] == 1, stats
        assert stats["ineligible"] == 1, stats
        assert fake.calls == 2

        row = conn.execute(
            "SELECT status FROM jobs WHERE game_id='g1'"
        ).fetchone()
        assert row["status"] == "done"

        result = conn.execute(
            "SELECT canonical_title,release_date,genres_json,raw_json FROM results WHERE game_id='g1'"
        ).fetchone()
        assert result["canonical_title"] == "Example Game"
        assert result["release_date"] == "2024-05-01"
        assert json.loads(result["genres_json"]) == ["Adventure game"]
        raw = json.loads(result["raw_json"])
        assert raw["method"] == "review_llm_candidate_v1"
        assert raw["candidate"]["id"] == "Q100"

        assert conn.execute("SELECT status FROM jobs WHERE game_id='g2'").fetchone()["status"] == "review"
        assert conn.execute("SELECT status FROM jobs WHERE game_id='g3'").fetchone()["status"] == "review"

        # Terminal unresolved/ineligible states are not sent back to the model on
        # every timer activation.
        second = FakeLLM([])
        stats2 = worker.run_reviews(
            conn,
            {game["id"]: game for game in games},
            second,
            limit=10,
            confidence_threshold=0.92,
            max_error_attempts=3,
        )
        assert stats2["llm_calls"] == 0, stats2
        assert second.calls == 0

        # A pending first-stage job blocks the review resolver completely.
        conn.execute("UPDATE jobs SET status='pending' WHERE game_id='g2'")
        conn.commit()
        busy, pending, processing = worker.first_stage_busy(conn)
        assert busy and pending == 1 and processing == 0

        conn.close()

    print("review llm autodrain OK")


if __name__ == "__main__":
    main()
