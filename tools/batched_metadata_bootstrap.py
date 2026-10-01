#!/usr/bin/env python3
"""Non-blocking, batched Wikidata metadata bootstrap.

Search requests are paced and performed once per uncached title. Candidate and
linked-entity reads are then grouped into wbgetentities batches (up to 50 IDs).
If Wikimedia signals rate limiting, maxlag or a transient service/network error,
the affected jobs are returned to pending immediately: this command never sits
through minute-long retry sleeps.
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

import httpx

from ai_catalog_bootstrap import (
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
from fast_metadata_bootstrap import (
    FAST_USER_AGENT,
    VIDEO_GAME_QID,
    cached_evidence,
    choose_candidate,
    claim_pending,
    clean_fast_title,
    ensure_cache,
    store_cache,
    store_match,
)

DEFAULT_REQUEST_INTERVAL = 0.40
DEFAULT_MAXLAG = 10


class TransientStop(RuntimeError):
    """Wikimedia asked us to stop this run and resume later."""


def chunks(values: Iterable[str], size: int = 50) -> Iterable[list[str]]:
    batch: list[str] = []
    for value in values:
        if value in batch:
            continue
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class BatchWikidataClient:
    def __init__(self, *, request_interval: float = DEFAULT_REQUEST_INTERVAL, maxlag: int = DEFAULT_MAXLAG):
        self.request_interval = max(0.0, request_interval)
        self.maxlag = max(1, maxlag)
        self._last_request = 0.0
        self.client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=True,
            headers={
                "User-Agent": FAST_USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "BatchWikidataClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _pace(self) -> None:
        now = time.monotonic()
        delay = self.request_interval - (now - self._last_request)
        if delay > 0:
            time.sleep(delay)
        self._last_request = time.monotonic()

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = dict(params)
        payload.setdefault("format", "json")
        payload.setdefault("maxlag", self.maxlag)
        self._pace()
        try:
            response = self.client.get(WIKIDATA_API, params=payload)
        except httpx.TransportError as exc:
            raise TransientStop(f"network: {exc}") from exc

        if response.status_code == 429 or 500 <= response.status_code < 600:
            retry_after = response.headers.get("Retry-After")
            suffix = f" retry_after={retry_after}" if retry_after else ""
            raise TransientStop(f"HTTP {response.status_code}{suffix}")

        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("unexpected Wikidata response")
        error = data.get("error")
        if isinstance(error, dict) and error.get("code") == "maxlag":
            lag = error.get("lag")
            raise TransientStop(f"maxlag lag={lag}")
        return data

    def search(self, title: str, limit: int) -> list[str]:
        data = self._get({
            "action": "wbsearchentities",
            "search": clean_fast_title(title),
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

    def entities(self, ids: list[str], props: str) -> dict[str, Any]:
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



def entity_label(entity: dict[str, Any]) -> str | None:
    labels = entity.get("labels") if isinstance(entity.get("labels"), dict) else {}
    for language in ("en", "fr"):
        item = labels.get(language)
        if isinstance(item, dict) and item.get("value"):
            return str(item["value"])
    return None


def description(entity: dict[str, Any]) -> str:
    descriptions = entity.get("descriptions") if isinstance(entity.get("descriptions"), dict) else {}
    for language in ("en", "fr"):
        item = descriptions.get(language)
        if isinstance(item, dict) and item.get("value"):
            return str(item["value"])
    return ""


def defer_jobs(conn: sqlite3.Connection, game_ids: list[str], reason: str) -> None:
    if not game_ids:
        return
    now = utcnow()
    conn.executemany(
        """
        UPDATE jobs
        SET status='pending',last_error=?,started_at=NULL,finished_at=NULL,updated_at=?
        WHERE game_id=?
        """,
        [(reason[:1200], now, game_id) for game_id in game_ids],
    )
    conn.commit()


def review_job(conn: sqlite3.Connection, game_id: str, reason: str) -> None:
    now = utcnow()
    conn.execute(
        "UPDATE jobs SET status='review',last_error=?,finished_at=?,updated_at=? WHERE game_id=?",
        (reason[:1200], now, now, game_id),
    )


def reset_status(conn: sqlite3.Connection, status: str) -> int:
    now = utcnow()
    cursor = conn.execute(
        """
        UPDATE jobs SET status='pending',last_error=NULL,started_at=NULL,finished_at=NULL,
        queued_at=?,updated_at=? WHERE active=1 AND status=?
        """,
        (now, now, status),
    )
    conn.commit()
    return cursor.rowcount


def build_candidate(qid: str, entity: dict[str, Any], linked_labels: dict[str, str]) -> dict[str, Any]:
    claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
    candidate: dict[str, Any] = {
        "source": "wikidata",
        "url": f"https://www.wikidata.org/wiki/{qid}",
        "id": qid,
        "label": entity_label(entity),
        "description": description(entity),
        "instance_of": _claim_entity_ids(claims, "P31"),
        "release_dates": _claim_times(claims, "P577"),
    }
    for prop, field in (
        ("P136", "genres"),
        ("P178", "developers"),
        ("P123", "publishers"),
        ("P400", "platforms"),
    ):
        candidate[field] = [
            linked_labels.get(value, value)
            for value in _claim_entity_ids(claims, prop)
        ]
    return candidate


def run_batched(
    conn: sqlite3.Connection,
    *,
    limit: int,
    candidate_limit: int,
    request_interval: float,
    maxlag: int,
    threshold: float,
    margin: float,
) -> dict[str, int]:
    ensure_cache(conn)
    claimed = claim_pending(conn, limit)
    if not claimed:
        return {"processed": 0, "done": 0, "review": 0, "failed": 0, "deferred": 0, "cache_hits": 0, "search_requests": 0, "entity_requests": 0}

    cached_by_id: dict[str, list[dict[str, Any]]] = {}
    misses: list[tuple[str, str]] = []
    for game_id, title in claimed:
        cached = cached_evidence(conn, title)
        if cached is None:
            misses.append((game_id, title))
        else:
            cached_by_id[game_id] = cached

    ids_by_game: dict[str, list[str]] = {}
    entities: dict[str, Any] = {}
    linked_labels: dict[str, str] = {}
    search_requests = 0
    entity_requests = 0
    deferred_ids: set[str] = set()

    with BatchWikidataClient(request_interval=request_interval, maxlag=maxlag) as api:
        # Search is the only inherently per-title operation. There are no retry sleeps.
        for index, (game_id, title) in enumerate(misses):
            try:
                ids_by_game[game_id] = api.search(title, candidate_limit)
                search_requests += 1
            except TransientStop as exc:
                # Wikimedia explicitly asks clients to stop after throttling. Defer every
                # uncached job from this run and exit the network phase immediately.
                deferred_ids.update(game for game, _ in misses)
                defer_jobs(conn, list(deferred_ids), f"wikidata transient: {exc}")
                break
            except Exception as exc:
                review_job(conn, game_id, f"wikidata search error: {exc}")
                ids_by_game[game_id] = []

        if not deferred_ids and ids_by_game:
            all_ids = sorted({qid for ids in ids_by_game.values() for qid in ids})
            try:
                for batch in chunks(all_ids, 50):
                    entities.update(api.entities(batch, "labels|descriptions|claims"))
                    entity_requests += 1

                linked_ids: set[str] = set()
                for entity in entities.values():
                    if not isinstance(entity, dict):
                        continue
                    claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
                    for prop in ("P136", "P178", "P123", "P400"):
                        linked_ids.update(_claim_entity_ids(claims, prop))

                for batch in chunks(sorted(linked_ids), 50):
                    label_entities = api.entities(batch, "labels")
                    entity_requests += 1
                    for qid, entity in label_entities.items():
                        if isinstance(entity, dict):
                            linked_labels[qid] = entity_label(entity) or qid
            except TransientStop as exc:
                deferred_ids.update(game_id for game_id, _ in misses)
                defer_jobs(conn, list(deferred_ids), f"wikidata transient: {exc}")

    evidence_by_id = dict(cached_by_id)
    if not deferred_ids:
        for game_id, title in misses:
            evidence: list[dict[str, Any]] = []
            for qid in ids_by_game.get(game_id, []):
                entity = entities.get(qid)
                if isinstance(entity, dict):
                    evidence.append(build_candidate(qid, entity, linked_labels))
            evidence_by_id[game_id] = evidence
            store_cache(conn, title, evidence)
        conn.commit()

    done = review = failed = 0
    for game_id, title in claimed:
        if game_id in deferred_ids:
            continue
        evidence = evidence_by_id.get(game_id)
        if evidence is None:
            # A permanent per-title search error was already moved to review.
            status = conn.execute("SELECT status FROM jobs WHERE game_id=?", (game_id,)).fetchone()
            if status and status["status"] == "review":
                review += 1
            continue
        match, confidence, reason = choose_candidate(
            clean_fast_title(title), evidence, threshold=threshold, margin=margin
        )
        if match is None:
            review_job(conn, game_id, reason)
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
        "deferred": len(deferred_ids),
        "cache_hits": len(cached_by_id),
        "search_requests": search_requests,
        "entity_requests": entity_requests,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Batched non-blocking Wikidata metadata bootstrap.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-review", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--candidate-limit", type=int, default=3)
    parser.add_argument("--request-interval", type=float, default=DEFAULT_REQUEST_INTERVAL)
    parser.add_argument("--maxlag", type=int, default=DEFAULT_MAXLAG)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--margin", type=float, default=0.08)
    args = parser.parse_args()

    if not any((args.init, args.run, args.status, args.retry_failed, args.retry_review)):
        parser.error("choose at least one action")
    if args.limit <= 0 or args.candidate_limit <= 0:
        parser.error("--limit and --candidate-limit must be greater than zero")

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
            print("batched run:", compact_json(run_batched(
                conn,
                limit=args.limit,
                candidate_limit=min(args.candidate_limit, 5),
                request_interval=max(0.0, args.request_interval),
                maxlag=max(1, args.maxlag),
                threshold=min(1.0, max(0.0, args.threshold)),
                margin=max(0.0, args.margin),
            )))
        if args.status or args.run or args.init:
            print("queue:", compact_json(queue_counts(conn)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
