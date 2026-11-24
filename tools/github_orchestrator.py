from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone

# Ordered tie-breaker: long-overdue work takes precedence over short periodic checks.
INTERVALS = {
    "steam-ratings.yml": 60,
    "backfill-catalog.yml": 1440,
    "update-catalog.yml": 60,
    "enrich-media.yml": 15,
    "feed-watch.yml": 10,
}
RETRY_MINUTES = 15


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def choose(runs, now):
    # Fail closed: missing workflow history must never be mistaken for an idle queue.
    if set(runs) != set(INTERVALS):
        raise ValueError("incomplete workflow history")
    if any(r["status"] != "completed" for history in runs.values() for r in history):
        return None, "writer or feed check already active"
    due = []
    for name, interval in INTERVALS.items():
        history = runs[name]
        successful = [r for r in history if r.get("conclusion") == "success"]
        latest = max(history, key=lambda r: timestamp(r["created_at"]), default=None)
        if latest and latest.get("conclusion") != "success":
            if now - timestamp(latest["updated_at"]) < timedelta(minutes=RETRY_MINUTES):
                continue
        if successful:
            last = max(timestamp(r.get("run_started_at") or r["created_at"]) for r in successful)
            overdue = (now - last).total_seconds() / 60 - interval
        else:
            overdue = float("inf")
        if overdue >= 0:
            due.append((overdue, name))
    if not due:
        return None, "all workflows fresh or cooling down"
    return max(due, key=lambda x: x[0])[1], "most overdue eligible workflow"


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Rzbck/FitBoyRepack")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    histories = {}
    for name in INTERVALS:
        path = f"repos/{args.repo}/actions/workflows/{name}/runs?branch=main&per_page=20"
        histories[name] = json.loads(gh("api", path))["workflow_runs"]
    name, reason = choose(histories, datetime.now(timezone.utc))
    print(f"Orchestrator: {name or 'idle'} ({reason})", flush=True)
    if name and not args.dry_run:
        subprocess.run(["gh", "workflow", "run", name, "--ref", "main", "-R", args.repo], check=True)


if __name__ == "__main__":
    main()
