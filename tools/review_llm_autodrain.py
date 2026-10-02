#!/usr/bin/env python3
"""Autonomous second-stage resolver for deterministic metadata reviews.

The first-stage V2 worker remains authoritative for discovery and structured
Wikidata retrieval. This worker only considers rows already in ``review`` and
only asks the local LLM to choose among cached, complete, game-like Wikidata
candidates. The model never supplies factual metadata: accepted fields are
copied from the selected Wikidata candidate.

Rows with no cached evidence, no complete game candidate, a low-confidence LLM
decision, or a null decision remain in review. A versioned SQLite state table
prevents the timer from asking the model about the same unresolved row forever.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import batched_metadata_bootstrap_v2 as v2
from ai_catalog_bootstrap import AI_VERSION, compact_json, utcnow
from llm_client import LocalLLMClient

base = v2.base

REVIEW_LLM_VERSION = 1
DEFAULT_DB = Path("/var/lib/fitboy/ai/catalog_enrichment.sqlite3")
DEFAULT_LOCK = Path("/var/lib/fitboy/ai/review-llm.lock")
DEFAULT_LIMIT = 12
DEFAULT_THRESHOLD = 0.92
DEFAULT_MAX_ERROR_ATTEMPTS = 3


def acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def ensure_state(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_review_state (
            game_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            worker_version INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('resolved','unresolved','ineligible','error')),
            attempts INTEGER NOT NULL DEFAULT 0,
            candidate_id TEXT,
            confidence REAL,
            reason TEXT,
            last_error TEXT,
            attempted_at TEXT NOT NULL,
            PRIMARY KEY(game_id, fingerprint, worker_version)
        )
        """
    )
    conn.commit()


def first_stage_busy(conn: sqlite3.Connection) -> tuple[bool, int, int]:
    counts = {
        row["status"]: int(row["n"])
        for row in conn.execute(
            "SELECT status,COUNT(*) AS n FROM jobs WHERE active=1 GROUP BY status"
        )
    }
    pending = counts.get("pending", 0)
    processing = counts.get("processing", 0)
    return pending > 0 or processing > 0, pending, processing


def _game_like(candidate: dict[str, Any]) -> bool:
    instances = {str(value) for value in candidate.get("instance_of") or []}
    description = str(candidate.get("description") or "").casefold()
    return base.VIDEO_GAME_QID in instances or "video game" in description


def _complete_candidate(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("id")
        and candidate.get("label")
        and candidate.get("url")
        and _game_like(candidate)
        and candidate.get("release_dates")
        and candidate.get("genres")
    )


def _candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate.get("id"),
        "label": candidate.get("label"),
        "description": candidate.get("description"),
        "release_dates": list(candidate.get("release_dates") or [])[:6],
        "genres": list(candidate.get("genres") or [])[:12],
        "developers": list(candidate.get("developers") or [])[:8],
        "publishers": list(candidate.get("publishers") or [])[:8],
        "platforms": list(candidate.get("platforms") or [])[:16],
        "url": candidate.get("url"),
    }


def build_decision_prompt(game: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str, str]:
    system = (
        "/no_think\n"
        "You resolve video-game identity using ONLY the supplied candidate list. "
        "Choose one candidate_id only when the catalog title clearly refers to that game. "
        "Ignore packaging/version/update/DLC/bonus/repack suffixes, but do not ignore meaningful game subtitles. "
        "Never invent a candidate or metadata. If the evidence is insufficient or ambiguous, candidate_id must be null. "
        "Return one JSON object only with candidate_id, confidence, and reason."
    )
    user = compact_json(
        {
            "task": "select the correct Wikidata candidate for this catalog entry",
            "source_entry": {
                "title": str(game.get("title") or ""),
                "genres": list(game.get("genres") or [])[:12],
            },
            "candidates": [_candidate_payload(item) for item in candidates],
            "required_schema": {
                "candidate_id": "string|null; must be one supplied candidate id",
                "confidence": "number 0..1",
                "reason": "short string",
            },
        }
    )
    return system, user


def _normalize_candidate_id(value: Any, allowed_ids: set[str]) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"null", "none", "unknown", "n/a"}:
        return None
    if text in allowed_ids:
        return text

    by_upper = {item.upper(): item for item in allowed_ids}
    matches = {
        match.upper()
        for match in re.findall(r"\bQ\d+\b", text, flags=re.I)
        if match.upper() in by_upper
    }
    if len(matches) == 1:
        return by_upper[next(iter(matches))]
    raise ValueError("LLM selected a candidate outside the supplied evidence")


def _normalize_confidence(value: Any) -> float:
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if text.endswith("%"):
            try:
                confidence = float(text[:-1].strip()) / 100.0
            except ValueError as exc:
                raise ValueError("LLM confidence is missing or invalid") from exc
        else:
            try:
                confidence = float(text)
            except ValueError as exc:
                raise ValueError("LLM confidence is missing or invalid") from exc
    else:
        try:
            confidence = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("LLM confidence is missing or invalid") from exc

    if not 0.0 <= confidence <= 1.0:
        raise ValueError("LLM confidence must be between 0 and 1")
    return confidence


def validate_decision(raw: dict[str, Any], allowed_ids: set[str]) -> tuple[str | None, float, str]:
    candidate_value = raw.get("candidate_id")
    if candidate_value is None:
        candidate_value = raw.get("candidate")
    if candidate_value is None:
        candidate_value = raw.get("id")
    candidate_id = _normalize_candidate_id(candidate_value, allowed_ids)

    confidence_value = raw.get("confidence")
    if confidence_value is None:
        confidence_value = raw.get("confidence_score")
    confidence = _normalize_confidence(confidence_value)

    reason_value = raw.get("reason")
    if reason_value is None:
        reason_value = raw.get("rationale")
    reason = re.sub(r"\s+", " ", str(reason_value or "")).strip()[:600]
    return candidate_id, confidence, reason


def parse_decision_response(text: str, allowed_ids: set[str]) -> tuple[str | None, float, str]:
    value = text.strip()
    if not value:
        raise ValueError("LLM response is empty")

    unfenced = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", value, flags=re.I)
    unfenced = re.sub(r"\s*\x60\x60\x60$", "", unfenced)

    parsed: Any = None
    try:
        parsed = json.loads(unfenced)
    except json.JSONDecodeError:
        start = unfenced.find("{")
        end = unfenced.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(unfenced[start : end + 1])
            except json.JSONDecodeError:
                parsed = None

    if isinstance(parsed, dict):
        return validate_decision(parsed, allowed_ids)

    compact = re.sub(r"\s+", " ", unfenced).strip()
    qids = {
        match.upper()
        for match in re.findall(r"\bQ\d+\b", compact, flags=re.I)
        if match.upper() in {item.upper() for item in allowed_ids}
    }
    if len(qids) > 1:
        raise ValueError("LLM text response mentions multiple supplied candidates")

    candidate_id: str | None
    if len(qids) == 1:
        by_upper = {item.upper(): item for item in allowed_ids}
        candidate_id = by_upper[next(iter(qids))]
    elif re.search(r"\b(?:candidate(?:_id)?\s*[:=]?\s*)?(?:null|none|unknown|n/a)\b", compact, flags=re.I):
        candidate_id = None
    else:
        raise ValueError("LLM text response contains no usable supplied candidate")

    confidence_match = re.search(
        r"\bconfidence(?:_score)?\s*[:=]?\s*(\d+(?:[.,]\d+)?\s*%?)",
        compact,
        flags=re.I,
    )
    if confidence_match is None:
        raise ValueError("LLM text response is missing explicit confidence")
    confidence = _normalize_confidence(confidence_match.group(1))

    return candidate_id, confidence, compact[:600]


def record_state(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    fingerprint: str,
    status: str,
    candidate_id: str | None = None,
    confidence: float | None = None,
    reason: str | None = None,
    error: str | None = None,
) -> None:
    previous = conn.execute(
        """
        SELECT attempts FROM llm_review_state
        WHERE game_id=? AND fingerprint=? AND worker_version=?
        """,
        (game_id, fingerprint, REVIEW_LLM_VERSION),
    ).fetchone()
    attempts = int(previous["attempts"]) + 1 if previous else 1
    conn.execute(
        """
        INSERT INTO llm_review_state(
            game_id,fingerprint,worker_version,status,attempts,candidate_id,
            confidence,reason,last_error,attempted_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(game_id,fingerprint,worker_version) DO UPDATE SET
            status=excluded.status,
            attempts=excluded.attempts,
            candidate_id=excluded.candidate_id,
            confidence=excluded.confidence,
            reason=excluded.reason,
            last_error=excluded.last_error,
            attempted_at=excluded.attempted_at
        """,
        (
            game_id,
            fingerprint,
            REVIEW_LLM_VERSION,
            status,
            attempts,
            candidate_id,
            confidence,
            reason,
            error[:1200] if error else None,
            utcnow(),
        ),
    )


def store_resolved_match(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    candidate: dict[str, Any],
    confidence: float,
    reason: str,
) -> None:
    checked = utcnow()
    releases = list(candidate.get("release_dates") or [])
    developers = list(candidate.get("developers") or [])
    publishers = list(candidate.get("publishers") or [])
    evidence = [str(candidate["url"])] if candidate.get("url") else []
    raw = {
        "method": "review_llm_candidate_v1",
        "candidate": candidate,
        "decision": {
            "candidate_id": candidate.get("id"),
            "confidence": confidence,
            "reason": reason,
        },
    }
    conn.execute(
        """
        INSERT INTO results(
          game_id,canonical_title,release_date,genres_json,developer,publisher,
          platforms_json,description_fr,confidence,evidence_json,notes,
          ai_version,checked_at,raw_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(game_id) DO UPDATE SET
          canonical_title=excluded.canonical_title,release_date=excluded.release_date,
          genres_json=excluded.genres_json,developer=excluded.developer,
          publisher=excluded.publisher,platforms_json=excluded.platforms_json,
          description_fr=excluded.description_fr,confidence=excluded.confidence,
          evidence_json=excluded.evidence_json,notes=excluded.notes,
          ai_version=excluded.ai_version,checked_at=excluded.checked_at,
          raw_json=excluded.raw_json
        """,
        (
            game_id,
            candidate.get("label"),
            releases[0],
            compact_json(candidate.get("genres") or []),
            developers[0] if developers else None,
            publishers[0] if publishers else None,
            compact_json(candidate.get("platforms") or []),
            None,
            confidence,
            compact_json(evidence),
            "local LLM selected a complete cached Wikidata candidate; factual fields copied from Wikidata",
            AI_VERSION,
            checked,
            compact_json(raw),
        ),
    )
    conn.execute(
        """
        UPDATE jobs
        SET status='done',last_error=NULL,finished_at=?,updated_at=?
        WHERE game_id=? AND status='review'
        """,
        (checked, checked, game_id),
    )


def review_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE active=1 AND status='review'"
    ).fetchone()
    return int(row["n"] if row else 0)


def run_reviews(
    conn: sqlite3.Connection,
    games_by_id: dict[str, dict[str, Any]],
    llm: LocalLLMClient,
    *,
    limit: int,
    confidence_threshold: float,
    max_error_attempts: int,
) -> dict[str, int]:
    ensure_state(conn)
    scanned = eligible = llm_calls = resolved = unresolved = ineligible = errors = 0

    rows = conn.execute(
        """
        SELECT j.game_id,j.title,j.fingerprint,j.last_error,
               s.status AS llm_status,s.attempts AS llm_attempts
        FROM jobs AS j
        LEFT JOIN llm_review_state AS s
          ON s.game_id=j.game_id
         AND s.fingerprint=j.fingerprint
         AND s.worker_version=?
        WHERE j.active=1
          AND j.status='review'
          AND (
            s.game_id IS NULL OR
            (s.status='error' AND s.attempts < ?)
          )
        ORDER BY j.updated_at,j.game_id
        """,
        (REVIEW_LLM_VERSION, max_error_attempts),
    ).fetchall()

    for row in rows:
        if llm_calls >= limit:
            break

        busy, pending, processing = first_stage_busy(conn)
        if busy:
            print(
                f"[LLM-REVIEW] yielding to V2 pending={pending} processing={processing}",
                flush=True,
            )
            break

        scanned += 1
        game_id = str(row["game_id"])
        title = str(row["title"])
        fingerprint = str(row["fingerprint"])
        game = games_by_id.get(game_id)
        if game is None:
            record_state(
                conn,
                game_id=game_id,
                fingerprint=fingerprint,
                status="ineligible",
                reason="catalog entry missing",
            )
            conn.commit()
            ineligible += 1
            continue

        evidence = base.cached_evidence(conn, title)
        if not evidence:
            record_state(
                conn,
                game_id=game_id,
                fingerprint=fingerprint,
                status="ineligible",
                reason="no cached Wikidata evidence",
            )
            conn.commit()
            ineligible += 1
            continue

        candidates = [item for item in evidence if isinstance(item, dict) and _complete_candidate(item)]
        if not candidates:
            record_state(
                conn,
                game_id=game_id,
                fingerprint=fingerprint,
                status="ineligible",
                reason="no complete game-like Wikidata candidate",
            )
            conn.commit()
            ineligible += 1
            continue

        eligible += 1
        allowed = {str(item["id"]): item for item in candidates}
        system, prompt = build_decision_prompt(game, candidates)
        try:
            llm_calls += 1
            response_text = llm.chat(
                prompt,
                system=system,
                temperature=0.0,
                max_tokens=240,
            )
            candidate_id, confidence, reason = parse_decision_response(
                response_text,
                set(allowed),
            )
            if candidate_id is not None and confidence >= confidence_threshold:
                candidate = allowed[candidate_id]
                store_resolved_match(
                    conn,
                    game_id=game_id,
                    candidate=candidate,
                    confidence=confidence,
                    reason=reason,
                )
                record_state(
                    conn,
                    game_id=game_id,
                    fingerprint=fingerprint,
                    status="resolved",
                    candidate_id=candidate_id,
                    confidence=confidence,
                    reason=reason,
                )
                resolved += 1
                outcome = "resolved"
            else:
                record_state(
                    conn,
                    game_id=game_id,
                    fingerprint=fingerprint,
                    status="unresolved",
                    candidate_id=candidate_id,
                    confidence=confidence,
                    reason=reason or "LLM declined or confidence below threshold",
                )
                unresolved += 1
                outcome = "unresolved"
            conn.commit()
            print(
                f"[LLM-REVIEW] game_id={game_id} outcome={outcome} "
                f"candidate={candidate_id or '-'} confidence={confidence:.3f}",
                flush=True,
            )
        except Exception as exc:
            record_state(
                conn,
                game_id=game_id,
                fingerprint=fingerprint,
                status="error",
                error=str(exc),
                reason="LLM request/validation error",
            )
            conn.commit()
            errors += 1
            detail = re.sub(r"\s+", " ", str(exc)).strip()[:240] or "unspecified"
            print(
                f"[LLM-REVIEW] game_id={game_id} outcome=error "
                f"type={type(exc).__name__} detail={detail!r}",
                flush=True,
            )

    return {
        "scanned": scanned,
        "eligible": eligible,
        "llm_calls": llm_calls,
        "resolved": resolved,
        "unresolved": unresolved,
        "ineligible": ineligible,
        "errors": errors,
        "reviews_remaining": review_count(conn),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous evidence-gated local-LLM review resolver.")
    parser.add_argument("--catalog", type=Path, default=base.DEFAULT_CATALOG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="maximum LLM calls per activation")
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-error-attempts", type=int, default=DEFAULT_MAX_ERROR_ATTEMPTS)
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be greater than zero")
    if not 0.0 <= args.confidence_threshold <= 1.0:
        parser.error("--confidence-threshold must be between 0 and 1")
    if args.max_error_attempts <= 0:
        parser.error("--max-error-attempts must be greater than zero")

    lock = acquire_lock(args.lock_file)
    if lock is None:
        print("[LLM-REVIEW] another review resolver already holds the lock; exiting", flush=True)
        return 0

    try:
        games = base.load_games(args.catalog)
        games_by_id = {str(game["id"]): game for game in games}
        conn = base.connect_db(args.db)
        try:
            ensure_state(conn)
            busy, pending, processing = first_stage_busy(conn)
            print("[LLM-REVIEW] queue_before=", compact_json(base.queue_counts(conn)), sep="", flush=True)
            if busy:
                print(
                    f"[LLM-REVIEW] V2 has priority; skipping pending={pending} processing={processing}",
                    flush=True,
                )
                return 0

            with LocalLLMClient() as llm:
                stats = run_reviews(
                    conn,
                    games_by_id,
                    llm,
                    limit=args.limit,
                    confidence_threshold=args.confidence_threshold,
                    max_error_attempts=args.max_error_attempts,
                )
            print("[LLM-REVIEW] run=", compact_json(stats), sep="", flush=True)
            print("[LLM-REVIEW] queue_after=", compact_json(base.queue_counts(conn)), sep="", flush=True)
        finally:
            conn.close()
    finally:
        lock.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
