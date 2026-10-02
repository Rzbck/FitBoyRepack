#!/usr/bin/env python3
"""Export a minimal public metadata snapshot from the private enrichment SQLite DB.

Only active, completed rows above the confidence threshold are exported. Internal
worker state, prompts, raw model output, notes and errors never leave the VPS.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_DB = Path("/var/lib/fitboy/ai/catalog_enrichment.sqlite3")
DEFAULT_OUTPUT = Path("/var/lib/fitboy/ai/metadata-enrichment.json")
PUBLIC_METADATA_VERSION = 1
DEFAULT_MIN_CONFIDENCE = 0.90
WIKIDATA_QID_RE = re.compile(r"^Q\d+$", re.I)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_list(value: object, maximum: int) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text[:180])
        if len(out) >= maximum:
            break
    return out


def _public_evidence_urls(value: object) -> list[str]:
    urls = _json_list(value, 10)
    out: list[str] = []
    for raw in urls:
        try:
            parsed = urlparse(raw)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            continue
        if not (
            host == "www.wikidata.org"
            or host.endswith(".wikipedia.org")
        ):
            continue
        clean = parsed._replace(fragment="").geturl()
        if clean not in out:
            out.append(clean)
    return out[:6]


def _clean_text(value: object, maximum: int) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:maximum] or None


def _snapshot_entry(row: sqlite3.Row) -> dict[str, object] | None:
    canonical = _clean_text(row["canonical_title"], 300)
    release = _clean_text(row["release_date"], 32)
    genres = _json_list(row["genres_json"], 12)
    confidence = float(row["confidence"])
    evidence = _public_evidence_urls(row["evidence_json"])

    if not canonical or not release or not genres or not evidence:
        return None

    entry: dict[str, object] = {
        "canonical_title": canonical,
        "release_date": release,
        "genres": genres,
        "confidence": round(confidence, 4),
        "evidence_urls": evidence,
        "checked_at": _clean_text(row["checked_at"], 64),
    }

    developer = _clean_text(row["developer"], 300)
    publisher = _clean_text(row["publisher"], 300)
    platforms = _json_list(row["platforms_json"], 24)
    if developer:
        entry["developer"] = developer
    if publisher:
        entry["publisher"] = publisher
    if platforms:
        entry["platforms"] = platforms

    first = evidence[0]
    match = re.search(r"/wiki/(Q\d+)$", first, flags=re.I)
    if match and WIKIDATA_QID_RE.fullmatch(match.group(1)):
        entry["wikidata_id"] = match.group(1).upper()

    return entry


def export_snapshot(db_path: Path, output_path: Path, min_confidence: float) -> dict[str, object]:
    if not db_path.exists():
        raise FileNotFoundError(f"metadata database not found: {db_path}")

    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              j.game_id,
              r.canonical_title,
              r.release_date,
              r.genres_json,
              r.developer,
              r.publisher,
              r.platforms_json,
              r.confidence,
              r.evidence_json,
              r.checked_at
            FROM jobs AS j
            JOIN results AS r ON r.game_id=j.game_id
            WHERE j.active=1
              AND j.status='done'
              AND r.confidence>=?
            ORDER BY j.game_id
            """,
            (min_confidence,),
        ).fetchall()
    finally:
        conn.close()

    games: dict[str, dict[str, object]] = {}
    skipped_incomplete = 0
    for row in rows:
        game_id = str(row["game_id"] or "").strip()
        if not game_id:
            skipped_incomplete += 1
            continue
        entry = _snapshot_entry(row)
        if entry is None:
            skipped_incomplete += 1
            continue
        games[game_id] = entry

    payload: dict[str, object] = {
        "metadata_version": PUBLIC_METADATA_VERSION,
        "generated_at": utcnow(),
        "minimum_confidence": min_confidence,
        "count": len(games),
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
        "exported": len(games),
        "eligible_rows": len(rows),
        "skipped_incomplete": skipped_incomplete,
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export verified public game metadata from SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    args = parser.parse_args()

    if not 0 <= args.min_confidence <= 1:
        parser.error("--min-confidence must be between 0 and 1")

    stats = export_snapshot(args.db, args.output, args.min_confidence)
    print(
        "public metadata export: "
        f"exported={stats['exported']} "
        f"eligible_rows={stats['eligible_rows']} "
        f"skipped_incomplete={stats['skipped_incomplete']} "
        f"output={stats['output']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
