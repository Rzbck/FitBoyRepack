#!/usr/bin/env python3
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx

import enrich_media_v6 as v6

base = v6.base
MEDIA_VERSION = v6.MEDIA_VERSION
DETAILS_VERSION = base.DETAILS_VERSION
MAX_TOTAL_WORKERS = 24
DEFAULT_TOTAL_WORKERS = 20
DEFAULT_GROUPS = 4


def parse_args():
    parser = argparse.ArgumentParser(
        description="Enrich catalog media through parallel worker groups while keeping one catalog writer."
    )
    parser.add_argument("--batch", type=int, default=720, help="Maximum games to enrich in one clustered round.")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_TOTAL_WORKERS,
        help=f"Total parallel HTTP workers shared by all groups (max {MAX_TOTAL_WORKERS}).",
    )
    parser.add_argument("--groups", type=int, default=DEFAULT_GROUPS, help="Independent parallel connection-pool groups.")
    parser.add_argument("--refresh", action="store_true", help="Recheck entries already on current parser versions.")
    return parser.parse_args()


def partition_candidates(items, groups):
    if not items:
        return []
    count = max(1, min(int(groups), len(items)))
    shards = [[] for _ in range(count)]
    for index, item in enumerate(items):
        shards[index % count].append(item)
    return [shard for shard in shards if shard]


def worker_allocation(total_workers, group_count):
    total_workers = max(group_count, min(int(total_workers), MAX_TOTAL_WORKERS))
    base_workers, remainder = divmod(total_workers, group_count)
    return [base_workers + (1 if index < remainder else 0) for index in range(group_count)]


def run_group(group_index, games, workers):
    updates = {}
    failures = 0
    messages = []
    with httpx.Client(
        headers=base.HEADERS,
        timeout=httpx.Timeout(25.0, connect=15.0),
        limits=httpx.Limits(max_connections=workers + 2, max_keepalive_connections=workers),
        follow_redirects=True,
        http2=True,
    ) as client:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"media-g{group_index}") as executor:
            futures = {executor.submit(base.enrich_one, client, game): game["id"] for game in games}
            for future in as_completed(futures):
                game_id = futures[future]
                try:
                    _, media, details = future.result()
                    updates[game_id] = (media, details)
                    gif_count = sum(1 for item in media if item.get("type") == "gif")
                    messages.append(
                        f"group {group_index}: {game_id}: {len(media)} media ({gif_count} gif); "
                        f"description={'yes' if details.get('description') else 'no'}"
                    )
                except Exception as exc:
                    failures += 1
                    messages.append(f"group {group_index}: {game_id}: ERROR {type(exc).__name__}: {exc}")
    return updates, failures, messages


def main():
    args = parse_args()
    payload = base.load_catalog()
    games = payload["games"]

    candidates = [
        game for game in games
        if game.get("source_url") and (
            args.refresh
            or game.get("media_version") != MEDIA_VERSION
            or game.get("details_version") != DETAILS_VERSION
        )
    ]
    candidates.sort(key=lambda game: game.get("post_date") or "", reverse=True)
    candidates = candidates[: max(1, args.batch)]
    if not candidates:
        print("No details/media enrichment work needed.")
        return

    total_workers = max(1, min(args.workers, MAX_TOTAL_WORKERS))
    group_count = max(1, min(args.groups, total_workers, len(candidates)))
    shards = partition_candidates(candidates, group_count)
    allocations = worker_allocation(total_workers, len(shards))

    print(
        f"details/media candidates: {len(candidates)}; groups: {len(shards)}; "
        f"total workers: {sum(allocations)}; group workers: {allocations}; "
        f"media=v{MEDIA_VERSION}; details=v{DETAILS_VERSION}"
    )

    updates = {}
    failures = 0
    with ThreadPoolExecutor(max_workers=len(shards), thread_name_prefix="media-group") as group_executor:
        futures = {
            group_executor.submit(run_group, index + 1, shard, allocations[index]): index + 1
            for index, shard in enumerate(shards)
        }
        for future in as_completed(futures):
            group_updates, group_failures, messages = future.result()
            updates.update(group_updates)
            failures += group_failures
            for message in messages:
                print(message)

    if not updates:
        print(f"No successful detail/media updates; failures={failures}")
        return

    checked_at = datetime.now(timezone.utc).isoformat()
    changed = 0
    for game in games:
        if game.get("id") not in updates:
            continue
        new_media, new_details = updates[game["id"]]
        if (
            game.get("media") != new_media
            or game.get("media_version") != MEDIA_VERSION
            or game.get("details") != new_details
            or game.get("details_version") != DETAILS_VERSION
            or not game.get("media_checked_at")
            or not game.get("details_checked_at")
        ):
            game["media"] = new_media
            game["media_version"] = MEDIA_VERSION
            game["media_checked_at"] = checked_at
            game["details"] = new_details
            game["details_version"] = DETAILS_VERSION
            game["details_checked_at"] = checked_at
            changed += 1

    if not changed:
        print("Details/media data unchanged.")
        return

    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    base.CATALOG.write_text(base.json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Clustered details/media enrichment updated {changed} games; failures={failures}; "
        f"groups={len(shards)}; workers={sum(allocations)}."
    )


if __name__ == "__main__":
    main()
