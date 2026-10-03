#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import export_public_translations as exporter
import publish_public_translations as publisher
import translation_autodrain as worker


def sample_game(description: str) -> dict[str, object]:
    return {
        "id": "alpha",
        "title": "Deep Sky Derelicts: Definitive Edition – v1.5.1 + Soundtrack",
        "details": {
            "description": description,
            "game_features": [
                "Explore the Deep Sky sector with your crew and discover lost stations.",
                "Build your squad and fight dangerous enemies in tactical battles.",
            ],
            "repack_features": [
                "This private operational text must never enter the translation queue."
            ],
        },
    }


def test_title_variants() -> None:
    blasphemous = worker.title_variants("Blasphemous 2: Mea Culpa")
    deep_sky = worker.title_variants("Deep Sky Derelicts")
    assert "Blasphemous" in blasphemous
    assert "Deep Sky" in deep_sky
    assert all("v1.5.1" not in item for item in worker.title_variants(
        "Deep Sky Derelicts: Definitive Edition – v1.5.1 + Soundtrack"
    ))


def test_queue_and_export(temp: Path) -> None:
    description = (
        "Explore the forgotten Deep Sky sector and uncover the secrets of abandoned ships. "
        "Build a team with different abilities and use careful tactics to survive every battle."
    )
    game = sample_game(description)
    metadata = {
        "alpha": {
            "canonical_title": "Deep Sky Derelicts",
            "developer": "Snowhound Games",
            "publisher": "Fulqrum Publishing",
        }
    }

    fields = worker.source_fields(game)
    assert [key for key, _text in fields] == [
        "description",
        "game_feature:0000",
        "game_feature:0001",
    ]
    assert all("private operational text" not in text for _key, text in fields)

    db = temp / "translations.sqlite3"
    conn = worker.connect_db(db)
    try:
        first = worker.sync_queue(conn, [game], metadata)
        assert first["queued"] == 3
        assert first["active"] == 3
        assert worker.queue_counts(conn)["pending"] == 3

        second = worker.sync_queue(conn, [game], metadata)
        assert second["queued"] == 0
        assert second["changed"] == 0
        assert second["unchanged"] == 3

        rows = conn.execute(
            "SELECT game_id,field_key,source_sha256 FROM translation_jobs ORDER BY field_key"
        ).fetchall()
        for row in rows:
            if row["field_key"] == "description":
                text = "Explorez le secteur Deep Sky et découvrez les secrets des vaisseaux abandonnés."
            elif row["field_key"] == "game_feature:0000":
                text = "Explorez le secteur Deep Sky avec votre équipage."
            else:
                text = "Constituez votre escouade et affrontez des ennemis dangereux."
            conn.execute(
                """
                UPDATE translation_jobs
                SET status='done',translated_text=?
                WHERE game_id=? AND field_key=?
                """,
                (text, row["game_id"], row["field_key"]),
            )
        conn.commit()

        changed_game = sample_game(
            description + " The world changes as you travel deeper into the unknown."
        )
        changed = worker.sync_queue(conn, [changed_game], metadata)
        assert changed["changed"] == 1
        assert worker.queue_counts(conn)["pending"] == 1

        # Restore the changed description as done so the public export has 3 fields.
        row = conn.execute(
            "SELECT source_sha256 FROM translation_jobs "
            "WHERE game_id='alpha' AND field_key='description'"
        ).fetchone()
        assert row is not None
        conn.execute(
            """
            UPDATE translation_jobs
            SET status='done',translated_text='Description française mise à jour.'
            WHERE game_id='alpha' AND field_key='description'
            """
        )
        conn.commit()
    finally:
        conn.close()

    output = temp / "translations-fr.json"
    stats = exporter.export_snapshot(db, output)
    assert stats["games"] == 1
    assert stats["fields"] == 3

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["translation_version"] == 1
    assert payload["language"] == "fr"
    assert payload["count"] == 1
    assert payload["field_count"] == 3
    assert set(payload["games"]) == {"alpha"}

    public = payload["games"]["alpha"]
    assert public["description"]["text"] == "Description française mise à jour."
    assert set(public["game_features"]) == {"0", "1"}
    assert len(public["description"]["source_sha256"]) == 64

    serialized = output.read_text(encoding="utf-8")
    assert "private operational text" not in serialized
    assert "source_text" not in serialized
    assert "last_error" not in serialized



def test_input_fingerprint_and_priority(temp: Path) -> None:
    catalog = temp / "games.json"
    metadata = temp / "metadata.json"
    catalog.write_text('{"games":[]}', encoding="utf-8")
    metadata.write_text('{"games":{}}', encoding="utf-8")

    first = worker.input_fingerprint(catalog, metadata)
    second = worker.input_fingerprint(catalog, metadata)
    assert first == second

    metadata.write_text('{"games":{"alpha":{}}}', encoding="utf-8")
    assert worker.input_fingerprint(catalog, metadata) != first

    db = temp / "priority.sqlite3"
    conn = worker.connect_db(db)
    try:
        game = sample_game(
            "This description contains enough English words to be queued for translation."
        )
        worker.sync_queue(conn, [game], {})
        rows = worker.pending_rows(conn, limit=3, max_error_attempts=3)
        assert rows
        assert rows[0]["field_key"] == "description"

        worker.set_meta_value(conn, "inputs_fingerprint", "abc")
        assert worker.meta_value(conn, "inputs_fingerprint") == "abc"

        conn.execute(
            "UPDATE translation_jobs SET status='processing' WHERE field_key='description'"
        )
        conn.commit()
        assert worker.recover_interrupted(conn) == 1
        status = conn.execute(
            "SELECT status FROM translation_jobs WHERE field_key='description'"
        ).fetchone()[0]
        assert status == "pending"
    finally:
        conn.close()


def test_publisher_semantic_noop(temp: Path) -> None:
    snapshot = temp / "translations-fr.json"
    payload = {
        "translation_version": 1,
        "language": "fr",
        "model": worker.MODEL_ID,
        "worker_version": worker.WORKER_VERSION,
        "generated_at": "2026-10-03T00:00:00+00:00",
        "count": 1,
        "field_count": 1,
        "games": {
            "alpha": {
                "description": {
                    "source_sha256": "a" * 64,
                    "text": "Bonjour.",
                }
            }
        },
    }
    snapshot.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    remote = dict(payload)
    remote["generated_at"] = "2026-10-03T01:00:00+00:00"
    remote_bytes = (
        json.dumps(remote, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")

    original_remote = publisher._remote_content
    original_request = publisher._request_json
    writes: list[object] = []
    try:
        publisher._remote_content = lambda *_args, **_kwargs: ("remote-sha", remote_bytes)
        publisher._request_json = (
            lambda *_args, **_kwargs: writes.append((_args, _kwargs)) or {}
        )
        stats = publisher.publish_snapshot(
            snapshot,
            repository="Rzbck/FitBoyRepack",
            path="site/data/translations-fr.json",
            branch="main",
            token="test-token",
        )
    finally:
        publisher._remote_content = original_remote
        publisher._request_json = original_request

    assert stats["changed"] is False
    assert writes == []


def main() -> None:
    test_title_variants()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        test_queue_and_export(temp)
        test_input_fingerprint_and_priority(temp)
        test_publisher_semantic_noop(temp)
    print("French translation queue + export + idempotent publish OK")


if __name__ == "__main__":
    main()
