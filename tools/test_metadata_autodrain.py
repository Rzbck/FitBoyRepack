#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

import metadata_autodrain as auto


def game(game_id: str, title: str) -> dict:
    return {
        "id": game_id,
        "title": title,
        "source_url": f"https://example.invalid/{game_id}",
        "post_date": "2026-01-01",
        "genres": [],
        "details": {"description": "source"},
    }


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "queue.sqlite3"
        conn = auto.base.connect_db(db)

        first = auto.base.initialize_queue(
            conn,
            [game("1", "One"), game("2", "Two")],
        )
        assert first["created"] == 2

        conn.execute("UPDATE jobs SET status='done' WHERE game_id='1'")
        conn.execute("UPDATE jobs SET status='processing' WHERE game_id='2'")
        conn.commit()

        recovered = auto.base.initialize_queue(
            conn,
            [game("1", "One"), game("2", "Two"), game("3", "Three")],
        )
        assert recovered["created"] == 1
        assert recovered["recovered"] == 1
        assert conn.execute("SELECT status FROM jobs WHERE game_id='1'").fetchone()["status"] == "done"
        assert conn.execute("SELECT status FROM jobs WHERE game_id='2'").fetchone()["status"] == "pending"
        assert conn.execute("SELECT status FROM jobs WHERE game_id='3'").fetchone()["status"] == "pending"

        calls = []

        def fake_run_batch(conn, **kwargs):
            calls.append(kwargs["limit"])
            rows = conn.execute(
                "SELECT game_id FROM jobs WHERE active=1 AND status='pending' ORDER BY game_id LIMIT ?",
                (kwargs["limit"],),
            ).fetchall()
            done = review = 0
            for row in rows:
                if row["game_id"] == "2":
                    conn.execute("UPDATE jobs SET status='done' WHERE game_id=?", (row["game_id"],))
                    done += 1
                else:
                    conn.execute("UPDATE jobs SET status='review' WHERE game_id=?", (row["game_id"],))
                    review += 1
            conn.commit()
            return {
                "processed": len(rows),
                "done": done,
                "review": review,
                "failed": 0,
                "deferred": 0,
            }

        stats = auto.drain_pending(
            conn,
            batch_size=1,
            candidate_limit=3,
            request_interval=0,
            maxlag=10,
            threshold=0.9,
            margin=0.08,
            progress_every=0,
            cooldown=0,
            transient_cooldown=0,
            max_stagnant=2,
            max_batches=0,
            sleep_fn=lambda _seconds: None,
            run_batch=fake_run_batch,
        )

        assert calls == [1, 1]
        assert stats["pending"] == 0
        assert stats["done"] == 1
        assert stats["review"] == 1

        counts = auto.base.queue_counts(conn)
        assert counts["done"] == 2
        assert counts["review"] == 1
        conn.close()

    print("metadata autodrain OK")


if __name__ == "__main__":
    main()
