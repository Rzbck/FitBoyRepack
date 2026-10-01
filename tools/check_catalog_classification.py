#!/usr/bin/env python3
import json
from pathlib import Path

from catalog_classifier import classify_record

P = Path("site/data/games.json")
data = json.loads(P.read_text(encoding="utf-8"))

non_games = []
reviews = []
for game in data.get("games", []):
    decision = classify_record(game)
    if decision["kind"] == "non_game":
        non_games.append((game.get("id"), game.get("title"), decision["reason"]))
    elif decision["kind"] == "review":
        reviews.append((game.get("id"), game.get("title"), decision["reason"]))

if non_games:
    print("High-confidence non-game entries remain in games.json:")
    for game_id, title, reason in non_games[:50]:
        print(f"- {game_id}: {title} [{reason}]")
    raise SystemExit(f"classification guard failed: {len(non_games)} non-game entries")

print(f"classification guard OK: {len(data.get('games', []))} games; {len(reviews)} low-signal historical records retained for review")
