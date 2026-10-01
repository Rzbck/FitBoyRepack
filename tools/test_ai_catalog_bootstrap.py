#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_catalog_bootstrap import (
    clean_search_title,
    connect_db,
    initialize_queue,
    queue_counts,
    run_batch,
    validate_ai_result,
)


class FakeRetriever:
    def fetch(self, game, candidate_limit=4):
        if game["id"] == "missing":
            return []
        return [{
            "source": "wikidata",
            "url": f"https://www.wikidata.org/wiki/Q{game['id']}",
            "id": f"Q{game['id']}",
            "label": game["title"],
            "description": "video game",
            "release_dates": ["2020-01-02"],
            "genres": ["Action"],
            "developers": ["Studio"],
            "publishers": ["Publisher"],
            "platforms": ["Windows"],
        }]


class FakeLLM:
    def __init__(self, confidence=0.95):
        self.confidence = confidence
        self.calls = 0

    def chat_json(self, prompt, *, system, temperature=None, max_tokens=None):
        self.calls += 1
        qid = "Q1" if '"id":"1"' in prompt else "Q2"
        return {
            "canonical_title": "Canonical Game",
            "release_date": "2020-01-02",
            "genres": ["Action", "Adventure"],
            "developer": "Studio",
            "publisher": "Publisher",
            "platforms": ["Windows"],
            "description_fr": "Description française fidèle.",
            "confidence": self.confidence,
            "evidence_urls": [f"https://www.wikidata.org/wiki/{qid}"],
            "notes": None,
        }


def game(game_id, title="Game One"):
    return {
        "id": game_id,
        "title": title,
        "source_url": f"https://example.invalid/{game_id}",
        "post_date": "2026-01-01",
        "genres": ["Action"],
        "details": {"description": "English source description."},
    }


def main():
    assert clean_search_title("Example Game + DLCs + Bonus") == "Example Game"
    assert clean_search_title("Example Game v1.2.3") == "Example Game"

    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "ai.sqlite3"
        conn = connect_db(db)
        games = [game("1"), game("2", "Game Two"), game("missing", "Unknown")]
        stats = initialize_queue(conn, games)
        assert stats["created"] == 3 and stats["total"] == 3
        assert queue_counts(conn)["pending"] == 3

        reliable = FakeLLM(0.96)
        result = run_batch(conn, {g["id"]: g for g in games}, reliable, FakeRetriever(), limit=1, threshold=0.80)
        assert result == {"processed": 1, "done": 1, "review": 0, "failed": 0}
        row = conn.execute("SELECT status FROM jobs WHERE game_id='1'").fetchone()
        assert row["status"] == "done"
        stored = conn.execute("SELECT release_date,confidence FROM results WHERE game_id='1'").fetchone()
        assert stored["release_date"] == "2020-01-02" and stored["confidence"] == 0.96

        uncertain = FakeLLM(0.55)
        result = run_batch(conn, {g["id"]: g for g in games}, uncertain, FakeRetriever(), limit=1, threshold=0.80)
        assert result["review"] == 1
        assert conn.execute("SELECT status FROM jobs WHERE game_id='2'").fetchone()["status"] == "review"

        result = run_batch(conn, {g["id"]: g for g in games}, FakeLLM(), FakeRetriever(), limit=1)
        assert result["failed"] == 1
        assert conn.execute("SELECT status FROM jobs WHERE game_id='missing'").fetchone()["status"] == "failed"

        changed = [game("1", "Game One Updated"), game("2", "Game Two"), game("missing", "Unknown")]
        refresh = initialize_queue(conn, changed)
        assert refresh["changed"] == 1
        assert conn.execute("SELECT status FROM jobs WHERE game_id='1'").fetchone()["status"] == "pending"
        assert conn.execute("SELECT 1 FROM results WHERE game_id='1'").fetchone() is None
        conn.close()

    allowed = {"https://www.wikidata.org/wiki/Q1"}
    cleaned = validate_ai_result({
        "canonical_title": "Game", "release_date": "2020-01-02", "genres": ["Action"],
        "developer": "Studio", "publisher": "Pub", "platforms": ["Windows"],
        "description_fr": "Texte", "confidence": 0.9,
        "evidence_urls": ["https://www.wikidata.org/wiki/Q1", "https://evil.invalid/fake"],
    }, allowed)
    assert cleaned["evidence_urls"] == ["https://www.wikidata.org/wiki/Q1"]

    try:
        validate_ai_result({"canonical_title": "Game", "confidence": 0.9, "download_url": "x"}, allowed)
    except ValueError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("forbidden LLM output field was accepted")

    print("AI catalog bootstrap OK")


if __name__ == "__main__":
    main()
