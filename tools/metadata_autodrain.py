#!/usr/bin/env python3
"""Autonomous, resumable V2 metadata drain for the FitBoy catalog.

This process is designed to be run by systemd. Each activation first syncs the
SQLite queue with the current catalog (including recovery of interrupted
`processing` rows), then drains `pending` rows in bounded V2 batches. Transient
Wikimedia throttling does not become a permanent failure: the drain cools down
and retries a limited number of stagnant batches before exiting cleanly so the
systemd timer can try again later.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable

import batched_metadata_bootstrap_v2 as v2

base = v2.base

DEFAULT_DB = Path("/var/lib/fitboy/ai/catalog_enrichment.sqlite3")
DEFAULT_LOCK = Path("/var/lib/fitboy/ai/metadata-autodrain.lock")


def pending_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE active=1 AND status='pending'"
    ).fetchone()
    return int(row["n"] if row is not None else 0)


def drain_pending(
    conn: sqlite3.Connection,
    *,
    batch_size: int,
    candidate_limit: int,
    request_interval: float,
    maxlag: int,
    threshold: float,
    margin: float,
    progress_every: int,
    cooldown: float,
    transient_cooldown: float,
    max_stagnant: int,
    max_batches: int,
    sleep_fn: Callable[[float], None] = time.sleep,
    run_batch: Callable[..., dict[str, int]] = base.run_batched,
) -> dict[str, int]:
    batches = 0
    stagnant = 0
    processed = done = review = failed = deferred = 0

    while True:
        before = pending_count(conn)
        if before <= 0:
            break
        if max_batches > 0 and batches >= max_batches:
            break

        batches += 1
        limit = min(batch_size, before)
        print(
            f"[AUTODRAIN] batch={batches} pending_before={before} limit={limit}",
            flush=True,
        )

        stats = run_batch(
            conn,
            limit=limit,
            candidate_limit=candidate_limit,
            request_interval=request_interval,
            maxlag=maxlag,
            threshold=threshold,
            margin=margin,
            progress_every=progress_every,
        )

        after = pending_count(conn)
        progress = before - after
        processed += int(stats.get("processed", 0))
        done += int(stats.get("done", 0))
        review += int(stats.get("review", 0))
        failed += int(stats.get("failed", 0))
        deferred += int(stats.get("deferred", 0))

        print(
            "[AUTODRAIN] "
            f"batch={batches} pending_after={after} progress={progress} "
            f"done={stats.get('done', 0)} review={stats.get('review', 0)} "
            f"failed={stats.get('failed', 0)} deferred={stats.get('deferred', 0)}",
            flush=True,
        )

        if after <= 0:
            break

        if progress <= 0:
            stagnant += 1
            print(
                f"[AUTODRAIN] stagnant={stagnant}/{max_stagnant} "
                f"cooldown={transient_cooldown:.0f}s",
                flush=True,
            )
            if stagnant >= max_stagnant:
                print(
                    "[AUTODRAIN] stopping cleanly after repeated no-progress batches; "
                    "the systemd timer will retry later",
                    flush=True,
                )
                break
            sleep_fn(transient_cooldown)
        else:
            stagnant = 0
            if cooldown > 0:
                sleep_fn(cooldown)

    return {
        "batches": batches,
        "processed": processed,
        "done": done,
        "review": review,
        "failed": failed,
        "deferred": deferred,
        "pending": pending_count(conn),
    }


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous resumable V2 metadata drain.")
    parser.add_argument("--catalog", type=Path, default=base.DEFAULT_CATALOG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--candidate-limit", type=int, default=3)
    parser.add_argument("--request-interval", type=float, default=0.40)
    parser.add_argument("--maxlag", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--margin", type=float, default=0.08)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--cooldown", type=float, default=10.0)
    parser.add_argument("--transient-cooldown", type=float, default=120.0)
    parser.add_argument("--max-stagnant", type=int, default=3)
    parser.add_argument(
        "--max-batches",
        type=int,
        default=0,
        help="0 drains until pending is empty; positive values cap batches per activation",
    )
    args = parser.parse_args()

    if args.batch_size <= 0 or args.candidate_limit <= 0:
        parser.error("--batch-size and --candidate-limit must be greater than zero")
    if args.progress_every < 0 or args.max_stagnant <= 0 or args.max_batches < 0:
        parser.error("invalid progress/stagnant/batch limits")

    lock = acquire_lock(args.lock_file)
    if lock is None:
        print("[AUTODRAIN] another metadata drain already holds the lock; exiting", flush=True)
        return 0

    try:
        games = base.load_games(args.catalog)
        conn = base.connect_db(args.db)
        try:
            base.ensure_cache(conn)
            init_stats = base.initialize_queue(conn, games)
            print("[AUTODRAIN] queue_init=", base.compact_json(init_stats), sep="", flush=True)
            print("[AUTODRAIN] queue_before=", base.compact_json(base.queue_counts(conn)), sep="", flush=True)

            stats = drain_pending(
                conn,
                batch_size=args.batch_size,
                candidate_limit=min(args.candidate_limit, 5),
                request_interval=max(0.0, args.request_interval),
                maxlag=max(1, args.maxlag),
                threshold=min(1.0, max(0.0, args.threshold)),
                margin=max(0.0, args.margin),
                progress_every=args.progress_every,
                cooldown=max(0.0, args.cooldown),
                transient_cooldown=max(0.0, args.transient_cooldown),
                max_stagnant=args.max_stagnant,
                max_batches=args.max_batches,
            )

            print("[AUTODRAIN] drain=", base.compact_json(stats), sep="", flush=True)
            print("[AUTODRAIN] queue_after=", base.compact_json(base.queue_counts(conn)), sep="", flush=True)
        finally:
            conn.close()
    finally:
        lock.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
