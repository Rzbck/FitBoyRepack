#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
from pathlib import Path

DEFAULT_SOURCE = Path("site/data/games.json")
DEFAULT_SITE_ROOT = Path("site")
CATALOG_FILENAME = "catalog.json"
HEALTH_FILENAME = "health.json"
DETAILS_DIRNAME = "games"

LIGHT_FIELDS = (
    "id",
    "title",
    "source_url",
    "image_url",
    "post_date",
    "genres",
    "repack_size",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Build lightweight browser catalog + lazy per-game detail payloads.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    return parser.parse_args()


def detail_filename(game_id):
    digest = hashlib.sha256(str(game_id).encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def compact_dump(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def latest_stamp(*values):
    stamps = [str(value) for value in values if value]
    return max(stamps) if stamps else None


def main():
    args = parse_args()
    source_payload = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(source_payload, dict) or not isinstance(source_payload.get("games"), list):
        raise RuntimeError("source catalog must be an object with games: []")

    data_dir = args.site_root / "data"
    details_dir = data_dir / DETAILS_DIRNAME
    catalog_path = data_dir / CATALOG_FILENAME
    health_path = data_dir / HEALTH_FILENAME
    data_dir.mkdir(parents=True, exist_ok=True)

    if details_dir.exists():
        shutil.rmtree(details_dir)
    details_dir.mkdir(parents=True, exist_ok=True)

    catalog_games = []
    filenames = set()
    health = {
        "total": 0,
        "covers": 0,
        "details_ready": 0,
        "descriptions": 0,
        "game_features": 0,
        "repack_features": 0,
        "galleries": 0,
        "gifs": 0,
        "media_items": 0,
    }

    for game in source_payload["games"]:
        game_id = str(game.get("id") or "").strip()
        title = str(game.get("title") or "").strip()
        if not game_id or not title:
            continue

        filename = detail_filename(game_id)
        if filename in filenames:
            raise RuntimeError(f"detail filename collision for {game_id}")
        filenames.add(filename)

        detail_path = f"data/{DETAILS_DIRNAME}/{filename}"
        details = game.get("details") if isinstance(game.get("details"), dict) else {}
        media = game.get("media") if isinstance(game.get("media"), list) else []
        gif_count = sum(1 for item in media if isinstance(item, dict) and item.get("type") == "gif")
        has_description = bool(str(details.get("description") or "").strip())
        has_game_features = bool(details.get("game_features"))
        has_repack_features = bool(details.get("repack_features"))
        details_ready = game.get("details_version") is not None

        light = {key: game.get(key) for key in LIGHT_FIELDS if key in game}
        light["id"] = game_id
        light["title"] = title
        light["detail_path"] = detail_path
        light["details_ready"] = details_ready
        light["has_description"] = has_description
        light["has_game_features"] = has_game_features
        light["has_repack_features"] = has_repack_features
        light["media_count"] = len(media)
        light["gif_count"] = gif_count
        light["updated_at"] = latest_stamp(
            game.get("details_checked_at"),
            game.get("media_checked_at"),
            game.get("post_date"),
        )
        catalog_games.append(light)

        health["total"] += 1
        health["covers"] += int(bool(game.get("image_url")))
        health["details_ready"] += int(details_ready)
        health["descriptions"] += int(has_description)
        health["game_features"] += int(has_game_features)
        health["repack_features"] += int(has_repack_features)
        health["galleries"] += int(bool(media))
        health["gifs"] += int(gif_count > 0)
        health["media_items"] += len(media)

        compact_dump(details_dir / filename, game)

    generated_at = source_payload.get("generated_at")
    catalog_payload = {
        "catalog_version": source_payload.get("catalog_version"),
        "generated_at": generated_at,
        "count": len(catalog_games),
        "games": catalog_games,
    }
    health_payload = {
        "generated_at": generated_at,
        "catalog_version": source_payload.get("catalog_version"),
        **health,
    }
    compact_dump(catalog_path, catalog_payload)
    compact_dump(health_path, health_payload)

    source_bytes = args.source.stat().st_size
    catalog_bytes = catalog_path.stat().st_size
    ratio = (catalog_bytes / source_bytes) if source_bytes else 0
    print(
        f"site data built: {len(catalog_games)} games; "
        f"catalog={catalog_bytes / 1024:.1f} KiB; source={source_bytes / 1024:.1f} KiB; ratio={ratio:.3f}; "
        f"descriptions={health['descriptions']}; galleries={health['galleries']}; gifs={health['gifs']}"
    )


if __name__ == "__main__":
    main()
