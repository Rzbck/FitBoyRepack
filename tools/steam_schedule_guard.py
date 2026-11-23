#!/usr/bin/env python3
"""Prevent duplicate Steam batches when redundant GitHub schedules both fire."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path("site/data/steam-ratings.json")
FRESH_MINUTES = 40


def should_run(event, cache_path=CACHE, now=None):
    if event != "schedule":
        return True
    if not cache_path.exists():
        return True
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        age = (current - checked).total_seconds() / 60
        return not (0 <= age < FRESH_MINUTES)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        # Unknown state: let the normal cache validator fail safely.
        return True


if __name__ == "__main__":
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    run = should_run(event)
    print(f"run={'true' if run else 'false'}")
    print(f"Steam gate: {'RUN' if run else 'SKIP recent successful batch'}; event={event}", file=sys.stderr)
