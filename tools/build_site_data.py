#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SOURCE = Path("site/data/games.json")
DEFAULT_SITE_ROOT = Path("site")
CATALOG_FILENAME = "catalog.json"
HEALTH_FILENAME = "health.json"
DETAILS_DIRNAME = "games"
EXPECTED_MEDIA_VERSION = 6
EXPECTED_DETAILS_VERSION = 1
LIGHT_FIELDS = ("id", "title", "source_url", "image_url", "post_date", "genres", "repack_size")
SIZE_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(TB|TiB|GB|GiB|MB|MiB)", re.I)


def parse_args():
    parser = argparse.ArgumentParser(description="Build lightweight browser catalog + lazy per-game detail payloads.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    return parser.parse_args()


def detail_filename(game_id):
    return f"{hashlib.sha256(str(game_id).encode('utf-8')).hexdigest()[:24]}.json"


def compact_dump(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def parse_size_mb(value):
    if not value:
        return None
    matches = SIZE_RE.findall(str(value))
    if not matches:
        return None
    values = []
    for raw, unit in matches:
        number = float(raw.replace(",", "."))
        unit = unit.lower()
        if unit.startswith("t"):
            number *= 1024 * 1024
        elif unit.startswith("g"):
            number *= 1024
        values.append(number)
    return round(min(values), 2) if values else None


def year_from_date(value):
    match = re.match(r"^(20\d{2})", str(value or ""))
    return int(match.group(1)) if match else None


def newest_iso(*values):
    valid = [str(value) for value in values if value]
    return max(valid) if valid else None


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
    stats = {
        "total_games": 0,
        "details_ready": 0,
        "with_description": 0,
        "with_gallery": 0,
        "with_gif": 0,
        "media_items": 0,
        "enrichment_pending": 0,
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

        media = game.get("media") if isinstance(game.get("media"), list) else []
        details = game.get("details") if isinstance(game.get("details"), dict) else {}
        description = str(details.get("description") or "").strip()
        media_count = len(media)
        has_gif = any(isinstance(item, dict) and item.get("type") == "gif" and item.get("url") for item in media)
        details_ready = game.get("details_version") == EXPECTED_DETAILS_VERSION
        media_ready = game.get("media_version") == EXPECTED_MEDIA_VERSION
        pending = bool(game.get("source_url")) and not (details_ready and media_ready)

        detail_path = f"data/{DETAILS_DIRNAME}/{filename}"
        light = {key: game.get(key) for key in LIGHT_FIELDS if key in game}
        light.update({
            "id": game_id,
            "title": title,
            "detail_path": detail_path,
            "year": year_from_date(game.get("post_date")),
            "size_mb": parse_size_mb(game.get("repack_size")),
            "details_ready": details_ready,
            "has_description": bool(description),
            "media_count": media_count,
            "has_gif": has_gif,
            "detail_updated_at": newest_iso(game.get("details_checked_at"), game.get("media_checked_at")),
        })
        catalog_games.append(light)
        compact_dump(details_dir / filename, game)

        stats["total_games"] += 1
        stats["details_ready"] += int(details_ready)
        stats["with_description"] += int(bool(description))
        stats["with_gallery"] += int(media_count > 0)
        stats["with_gif"] += int(has_gif)
        stats["media_items"] += media_count
        stats["enrichment_pending"] += int(pending)

    generated_at = source_payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    catalog_payload = {
        "catalog_version": source_payload.get("catalog_version"),
        "generated_at": generated_at,
        "count": len(catalog_games),
        "games": catalog_games,
    }
    compact_dump(catalog_path, catalog_payload)

    total = max(1, stats["total_games"])
    health_payload = {
        "generated_at": generated_at,
        **stats,
        "coverage": {
            "details": round(stats["details_ready"] * 100 / total, 1),
            "descriptions": round(stats["with_description"] * 100 / total, 1),
            "galleries": round(stats["with_gallery"] * 100 / total, 1),
            "gifs": round(stats["with_gif"] * 100 / total, 1),
        },
        "expected_versions": {"details": EXPECTED_DETAILS_VERSION, "media": EXPECTED_MEDIA_VERSION},
    }
    compact_dump(health_path, health_payload)

    source_bytes = args.source.stat().st_size
    catalog_bytes = catalog_path.stat().st_size
    ratio = (catalog_bytes / source_bytes) if source_bytes else 0
    print(f"site data built: {len(catalog_games)} games; catalog={catalog_bytes / 1024:.1f} KiB; source={source_bytes / 1024:.1f} KiB; ratio={ratio:.3f}")
    print(
        "catalog health: "
        f"descriptions={stats['with_description']}/{stats['total_games']}; "
        f"galleries={stats['with_gallery']}/{stats['total_games']}; "
        f"gifs={stats['with_gif']}/{stats['total_games']}; "
        f"pending={stats['enrichment_pending']}"
    )


if __name__ == "__main__":
    main()
