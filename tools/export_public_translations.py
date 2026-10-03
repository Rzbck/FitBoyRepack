#!/usr/bin/env python3
"""Export sanitized public French translations from the private VPS SQLite DB."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("/var/lib/fitboy/translation/translations.sqlite3")
DEFAULT_OUTPUT = Path("/var/lib/fitboy/translation/translations-fr.json")
TRANSLATION_VERSION = 1
WORKER_VERSION = 1
MODEL_ID = "Helsinki-NLP/opus-mt-tc-big-en-fr"
FEATURE_RE = re.compile(r"^game_feature:(\d{4})$")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def export_snapshot(db_path: Path, output_path: Path) -> dict[str, object]:
    if not db_path.exists():
        raise FileNotFoundError(f"translation database not found: {db_path}")

    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT game_id,field_key,source_sha256,translated_text
            FROM translation_jobs
            WHERE active=1
              AND status='done'
              AND worker_version=?
              AND translated_text IS NOT NULL
            ORDER BY game_id,field_key
            """,
            (WORKER_VERSION,),
        ).fetchall()
    finally:
        conn.close()

    games: dict[str, dict[str, object]] = {}
    fields = 0
    for row in rows:
        game_id = str(row["game_id"] or "").strip()
        field_key = str(row["field_key"] or "").strip()
        source_hash = str(row["source_sha256"] or "").strip().lower()
        text = re.sub(r"\s+", " ", str(row["translated_text"] or "")).strip()

        if not game_id or not re.fullmatch(r"[0-9a-f]{64}", source_hash) or not text:
            continue

        game = games.setdefault(game_id, {})
        field_payload = {
            "source_sha256": source_hash,
            "text": text,
        }

        if field_key == "description":
            game["description"] = field_payload
            fields += 1
            continue

        match = FEATURE_RE.fullmatch(field_key)
        if not match:
            continue

        feature_index = str(int(match.group(1)))
        features = game.setdefault("game_features", {})
        if isinstance(features, dict):
            features[feature_index] = field_payload
            fields += 1

    payload: dict[str, object] = {
        "translation_version": TRANSLATION_VERSION,
        "language": "fr",
        "model": MODEL_ID,
        "worker_version": WORKER_VERSION,
        "generated_at": utcnow(),
        "count": len(games),
        "field_count": fields,
        "games": games,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(f".{output_path.name}.tmp-{os.getpid()}")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, output_path)

    return {
        "games": len(games),
        "fields": fields,
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export sanitized public French translations.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    stats = export_snapshot(args.db, args.output)
    print(
        "public translation export: "
        f"games={stats['games']} fields={stats['fields']} output={stats['output']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
