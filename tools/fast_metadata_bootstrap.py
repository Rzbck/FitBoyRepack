#!/usr/bin/env python3
"""Fast, resumable Wikidata metadata bootstrap without LLM inference.

The first pass intentionally avoids Wikipedia extracts and the local LLM. It
scores compact structured Wikidata candidates and stores only high-confidence
matches. Ambiguous/no-match rows go to review for a later LLM fallback.

Wikimedia public API access is globally paced across worker threads. HTTP 429,
5xx and maxlag responses are retried with Retry-After/exponential backoff and
remain pending if the transient condition persists.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sqlite3
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from ai_catalog_bootstrap import (
    AI_VERSION,
    DEFAULT_CATALOG,
    DEFAULT_DB,
    WIKIDATA_API,
    _claim_entity_ids,
    _claim_times,
    compact_json,
    connect_db,
    initialize_queue,
    load_games,
    queue_counts,
    utcnow,
)

VIDEO_GAME_QID = "Q7889"
DEFAULT_THRESHOLD = 0.90
DEFAULT_MARGIN = 0.08
DEFAULT_REQUEST_INTERVAL = 0.80
DEFAULT_MAX_RETRIES = 4
FAST_USER_AGENT = "FitBoyRepack-MetadataWorker/1.1 (https://github.com/Rzbck/FitBoyRepack)"

_REQUEST_LOCK = threading.Lock()
_NEXT_REQUEST_AT = 0.0


class TransientWikidataError(RuntimeError):
    """A rate-limit/service/network condition that should be retried later."""


def clean_fast_title(title: str) -> str:
    value = html.unescape(title).strip()
    value = re.sub(r"\s+\+\s+.*$", "", value)
    value = re.sub(
        r"(?:\s*[,–—-]\s*|\s+)v(?:ersion)?\s*\d[\w.\-]*(?:\s.*)?$",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(?:\s*[,–—-]\s*|\s+)build\s+\d+(?:\s.*)?$",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"\s*\((?:denuvoless|cracked?|portable)\)\s*$", "", value, flags=re.I)
    value = re.sub(r"\s{2,}", " ", value).strip(" ,;-–—")
    return value or title.strip()


def normalize_title(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def candidate_score(source_title: str, candidate: dict[str, Any]) -> float:
    source = normalize_title(source_title)
    label = normalize_title(str(candidate.get("label") or ""))
    if not source or not label:
        return 0.0

    exact = source == label
    sequence = difflib.SequenceMatcher(None, source, label).ratio()
    source_tokens = set(source.split())
    label_tokens = set(label.split())
    jaccard = len(source_tokens & label_tokens) / len(source_tokens | label_tokens)

    score = 0.76 if exact else (0.50 * sequence + 0.20 * jaccard)
    if not exact and (source in label or label in source):
        score += 0.08

    description = str(candidate.get("description") or "").casefold()
    game_like = VIDEO_GAME_QID in set(candidate.get("instance_of") or []) or "video game" in description
    if game_like:
        score += 0.12
    if candidate.get("release_dates"):
        score += 0.05
    if candidate.get("genres"):
        score += 0.04
    if candidate.get("developers") or candidate.get("publishers"):
        score += 0.03
    return min(score, 0.99)


def choose_candidate(
    source_title: str,
    candidates: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
) -> tuple[dict[str, Any] | None, float, str]:
    ranked = sorted(
        ((candidate_score(source_title, item), item) for item in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked:
        return None, 0.0, "no metadata evidence found"

    best_score, best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    description = str(best.get("description") or "").casefold()
    game_like = VIDEO_GAME_QID in set(best.get("instance_of") or []) or "video game" in description
    complete = bool(best.get("release_dates") and best.get("genres"))
    exact = normalize_title(source_title) == normalize_title(str(best.get("label") or ""))
    accepted = (
        best_score >= threshold
        and game_like
        and complete
        and (exact or best_score - second_score >= margin)
    )
    if accepted:
        return best, best_score, "accepted"
    return None, best_score, (
        f"ambiguous metadata match: best={best_score:.3f}, second={second_score:.3f}, "
        f"game_like={int(game_like)}, complete={int(complete)}"
    )


def _wait_for_request_slot(interval: float) -> None:
    global _NEXT_REQUEST_AT
    with _REQUEST_LOCK:
        now = time.monotonic()
        delay = max(0.0, _NEXT_REQUEST_AT - now)
        if delay:
            time.sleep(delay)
        _NEXT_REQUEST_AT = time.monotonic() + max(0.0, interval)


def _apply_global_backoff(seconds: float) -> None:
    global _NEXT_REQUEST_AT
    seconds = max(1.0, seconds)
    with _REQUEST_LOCK:
        _NEXT_REQUEST_AT = max(_NEXT_REQUEST_AT, time.monotonic() + seconds)


def _retry_after_seconds(value: str | None, attempt: int) -> float:
    if value:
        try:
            return max(1.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return max(1.0, (parsed - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return min(60.0, 5.0 * (2**attempt))


class FastWikidataRetriever:
    def __init__(
        self,
        *,
        request_interval: float = DEFAULT_REQUEST_INTERVAL,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.request_interval = max(0.0, request_interval)
        self.max_retries = max(0, max_retries)
        self.client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": FAST_USER_AGENT},
        )

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params.setdefault("format", "json")
        request_params.setdefault("maxlag", 5)

        for attempt in range(self.max_retries + 1):
            _wait_for_request_slot(self.request_interval)
            try:
                response = self.client.get(WIKIDATA_API, params=request_params)
            except httpx.TransportError as exc:
                delay = _retry_after_seconds(None, attempt)
                _apply_global_backoff(delay)
                if attempt >= self.max_retries:
                    raise TransientWikidataError(f"network error after retries: {exc}") from exc
                continue

            if response.status_code == 429 or 500 <= response.status_code < 600:
                delay = _retry_after_seconds(response.headers.get("Retry-After"), attempt)
                _apply_global_backoff(delay)
                if attempt >= self.max_retries:
                    raise TransientWikidataError(
                        f"HTTP {response.status_code} after retries; retry_after={delay:.1f}s"
                    )
                continue

            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError("unexpected Wikidata response")

            error = data.get("error")
            if isinstance(error, dict) and error.get("code") == "maxlag":
                delay = _retry_after_seconds(None, attempt)
                try:
                    delay = max(delay, float(error.get("lag") or 0.0))
                except (TypeError, ValueError):
                    pass
                _apply_global_backoff(delay)
                if attempt >= self.max_retries:
                    raise TransientWikidataError(f"maxlag after retries; retry_after={delay:.1f}s")
                continue

            return data

        raise TransientWikidataError("Wikidata retry budget exhausted")

    def _search(self, query: str, limit: int) -> list[str]:
        data = self._get({
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": limit,
        })
        return [
            str(item["id"])
            for item in data.get("search", [])
            if isinstance(item, dict) and item.get("id")
        ]

    def _entities(self, ids: list[str], props: str) -> dict[str, Any]:
        if not ids:
            return {}
        data = self._get({
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": props,
            "languages": "en|fr",
        })
        entities = data.get("entities")
        return entities if isinstance(entities, dict) else {}

    @staticmethod
    def _label(entity: dict[str, Any]) -> str | None:
        labels = entity.get("labels") if isinstance(entity.get("labels"), dict) else {}
        for language in ("en", "fr"):
            item = labels.get(language)
            if isinstance(item, dict) and item.get("value"):
                return str(item["value"])
        return None

    def fetch(self, title: str, candidate_limit: int) -> list[dict[str, Any]]:
        clean = clean_fast_title(title)
        ids: list[str] = []
        for query in (clean, title):
            for qid in self._search(query, candidate_limit):
                if qid not in ids:
                    ids.append(qid)
                if len(ids) >= candidate_limit:
                    break
            if len(ids) >= candidate_limit:
                break

        entities = self._entities(ids, "labels|descriptions|claims")
        linked_ids: set[str] = set()
        for entity in entities.values():
            if not isinstance(entity, dict):
                continue
            claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
            for prop in ("P136", "P178", "P123", "P400"):
                linked_ids.update(_claim_entity_ids(claims, prop))

        linked_entities = self._entities(sorted(linked_ids), "labels")
        labels = {
            qid: self._label(entity) or qid
            for qid, entity in linked_entities.items()
            if isinstance(entity, dict)
        }

        output: list[dict[str, Any]] = []
        for qid in ids:
            entity = entities.get(qid)
            if not isinstance(entity, dict):
                continue
            claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
            descriptions = entity.get("descriptions") if isinstance(entity.get("descriptions"), dict) else {}
            description = ""
            for language in ("en", "fr"):
                item = descriptions.get(language)
                if isinstance(item, dict) and item.get("value"):
                    description = str(item["value"])
                    break

            candidate: dict[str, Any] = {
                "source": "wikidata",
                "url": f"https://www.wikidata.org/wiki/{qid}",
                "id": qid,
                "label": self._label(entity),
                "description": description,
                "instance_of": _claim_entity_ids(claims, "P31"),
                "release_dates": _claim_times(claims, "P577"),
            }
            for prop, field in (
                ("P136", "genres"),
                ("P178", "developers"),
                ("P123", "publishers"),
                ("P400", "platforms"),
            ):
                candidate[field] = [labels.get(value, value) for value in _claim_entity_ids(claims, prop)]
            output.append(candidate)
        return output


_thread = threading.local()


def fetch_one(
    game_id: str,
    title: str,
    candidate_limit: int,
    request_interval: float,
) -> tuple[str, str, list[dict[str, Any]] | None, str | None]:
    try:
        retriever = getattr(_thread, "retriever", None)
        if retriever is None or retriever.request_interval != request_interval:
            retriever = FastWikidataRetriever(request_interval=request_interval)
            _thread.retriever = retriever
        return game_id, title, retriever.fetch(title, candidate_limit), None
    except TransientWikidataError as exc:
        return game_id, title, None, f"transient: {exc}"
    except httpx.TransportError as exc:
        return game_id, title, None, f"transient: network error: {exc}"
    except Exception as exc:
        return game_id, title, None, str(exc)[:1200]


def ensure_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata_cache (
            search_title TEXT PRIMARY KEY,
            evidence_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def cache_key(title: str) -> str:
    return normalize_title(clean_fast_title(title))


def cached_evidence(conn: sqlite3.Connection, title: str) -> list[dict[str, Any]] | None:
    row = conn.execute(
        "SELECT evidence_json FROM metadata_cache WHERE search_title=?",
        (cache_key(title),),
    ).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["evidence_json"])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def store_cache(conn: sqlite3.Connection, title: str, evidence: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO metadata_cache(search_title,evidence_json,fetched_at)
        VALUES(?,?,?)
        ON CONFLICT(search_title) DO UPDATE SET
          evidence_json=excluded.evidence_json,fetched_at=excluded.fetched_at
        """,
        (cache_key(title), compact_json(evidence), utcnow()),
    )


def set_status(conn: sqlite3.Connection, game_id: str, status: str, error: str | None = None) -> None:
    now = utcnow()
    conn.execute(
        "UPDATE jobs SET status=?,last_error=?,finished_at=?,updated_at=? WHERE game_id=?",
        (status, error[:1200] if error else None, now, now, game_id),
    )


def requeue_transient(conn: sqlite3.Connection, game_id: str, error: str) -> None:
    now = utcnow()
    conn.execute(
        """
        UPDATE jobs
        SET status='pending',last_error=?,started_at=NULL,finished_at=NULL,
            queued_at=?,updated_at=?
        WHERE game_id=?
        """,
        (error[:1200], now, now, game_id),
    )


def store_match(conn: sqlite3.Connection, game_id: str, candidate: dict[str, Any], confidence: float) -> None:
    checked = utcnow()
    releases = candidate.get("release_dates") or []
    developers = candidate.get("developers") or []
    publishers = candidate.get("publishers") or []
    evidence = [candidate["url"]] if candidate.get("url") else []
    raw = {"method": "fast_wikidata_v2", "candidate": candidate, "confidence": confidence}
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
            releases[0] if releases else None,
            compact_json(candidate.get("genres") or []),
            developers[0] if developers else None,
            publishers[0] if publishers else None,
            compact_json(candidate.get("platforms") or []),
            None,
            confidence,
            compact_json(evidence),
            "fast deterministic Wikidata match; French description pending",
            AI_VERSION,
            checked,
            compact_json(raw),
        ),
    )
    set_status(conn, game_id, "done")


def claim_pending(conn: sqlite3.Connection, limit: int) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT game_id,title FROM jobs WHERE active=1 AND status='pending' ORDER BY queued_at,game_id LIMIT ?",
        (limit,),
    ).fetchall()
    claimed: list[tuple[str, str]] = []
    now = utcnow()
    for row in rows:
        cursor = conn.execute(
            """
            UPDATE jobs SET status='processing',attempts=attempts+1,started_at=?,
            last_error=NULL,updated_at=? WHERE game_id=? AND status='pending'
            """,
            (now, now, row["game_id"]),
        )
        if cursor.rowcount == 1:
            claimed.append((str(row["game_id"]), str(row["title"])))
    conn.commit()
    return claimed


def run_fast_batch(
    conn: sqlite3.Connection,
    *,
    limit: int,
    workers: int,
    candidate_limit: int,
    threshold: float,
    margin: float,
    request_interval: float = DEFAULT_REQUEST_INTERVAL,
) -> dict[str, int]:
    ensure_cache(conn)
    claimed = claim_pending(conn, limit)
    evidence_by_id: dict[str, list[dict[str, Any]]] = {}
    misses: list[tuple[str, str]] = []
    cache_hits = failed = deferred = 0

    for game_id, title in claimed:
        cached = cached_evidence(conn, title)
        if cached is None:
            misses.append((game_id, title))
        else:
            cache_hits += 1
            evidence_by_id[game_id] = cached

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as pool:
        futures = [
            pool.submit(fetch_one, game_id, title, candidate_limit, request_interval)
            for game_id, title in misses
        ]
        for future in as_completed(futures):
            game_id, title, evidence, error = future.result()
            if error:
                if error.startswith("transient:"):
                    requeue_transient(conn, game_id, f"wikidata: {error}")
                    deferred += 1
                else:
                    set_status(conn, game_id, "failed", f"wikidata: {error}")
                    failed += 1
                continue
            evidence_by_id[game_id] = evidence or []
            store_cache(conn, title, evidence or [])

    done = review = 0
    for game_id, title in claimed:
        status = conn.execute("SELECT status FROM jobs WHERE game_id=?", (game_id,)).fetchone()
        if status is None or status["status"] != "processing":
            continue
        match, confidence, reason = choose_candidate(
            clean_fast_title(title),
            evidence_by_id.get(game_id, []),
            threshold=threshold,
            margin=margin,
        )
        if match is None:
            set_status(conn, game_id, "review", reason)
            review += 1
        else:
            store_match(conn, game_id, match, confidence)
            done += 1

    conn.commit()
    return {
        "processed": len(claimed),
        "done": done,
        "review": review,
        "failed": failed,
        "deferred": deferred,
        "cache_hits": cache_hits,
    }


def reset_status(conn: sqlite3.Connection, status: str) -> int:
    now = utcnow()
    cursor = conn.execute(
        """
        UPDATE jobs SET status='pending',last_error=NULL,started_at=NULL,
        finished_at=NULL,queued_at=?,updated_at=? WHERE active=1 AND status=?
        """,
        (now, now, status),
    )
    conn.commit()
    return cursor.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast Wikidata-first metadata bootstrap without LLM inference.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-review", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--candidate-limit", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL,
        help="minimum seconds between all Wikidata requests across worker threads",
    )
    args = parser.parse_args()

    if not any((args.init, args.run, args.status, args.retry_failed, args.retry_review)):
        parser.error("choose at least one action")
    if args.limit <= 0 or args.workers <= 0:
        parser.error("--limit and --workers must be greater than 0")
    if args.request_interval < 0:
        parser.error("--request-interval must be >= 0")
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    games = load_games(args.catalog)
    conn = connect_db(args.db)
    try:
        ensure_cache(conn)
        if args.init:
            print("queue init:", compact_json(initialize_queue(conn, games)))
        if args.retry_failed:
            print("requeued failed:", reset_status(conn, "failed"))
        if args.retry_review:
            print("requeued review:", reset_status(conn, "review"))
        if args.run:
            print("fast run:", compact_json(run_fast_batch(
                conn,
                limit=args.limit,
                workers=min(args.workers, 3),
                candidate_limit=max(1, min(args.candidate_limit, 5)),
                threshold=args.threshold,
                margin=max(0.0, args.margin),
                request_interval=args.request_interval,
            )))
        if args.status or args.run or args.init:
            print("queue:", compact_json(queue_counts(conn)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
