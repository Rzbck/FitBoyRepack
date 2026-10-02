#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SOURCE = Path("site/data/games.json")
DEFAULT_SITE_ROOT = Path("site")
CATALOG_FILENAME = "catalog.json"
SEARCH_INDEX_FILENAME = "search-index.json"
HEALTH_FILENAME = "health.json"
METADATA_FILENAME = "metadata-enrichment.json"
DETAILS_DIRNAME = "games"
EXPECTED_MEDIA_VERSION = 7
EXPECTED_DETAILS_VERSION = 1
EXPECTED_METADATA_VERSION = 1
SEARCH_INDEX_VERSION = 1
SEARCH_PREFIX_MIN = 2
SEARCH_PREFIX_MAX = 6
SEARCH_GRAM_SIZE = 3
LIGHT_FIELDS = ("id", "title", "source_url", "image_url", "post_date", "genres", "repack_size")
SIZE_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(TB|TiB|GB|GiB|MB|MiB)", re.I)
SEARCH_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def parse_args():
    parser = argparse.ArgumentParser(description="Build lightweight browser catalog + lazy per-game detail payloads.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="optional sanitized metadata snapshot; defaults beside the source catalog",
    )
    return parser.parse_args()


def detail_filename(game_id):
    return f"{hashlib.sha256(str(game_id).encode('utf-8')).hexdigest()[:24]}.json"


def compact_dump(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def load_public_metadata(path):
    if not path.exists():
        return {}, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("metadata_version") != EXPECTED_METADATA_VERSION:
        raise RuntimeError("public metadata snapshot has an unsupported version")
    games = payload.get("games")
    if not isinstance(games, dict):
        raise RuntimeError("public metadata snapshot must contain games: {}")
    if payload.get("count") != len(games):
        raise RuntimeError("public metadata snapshot count mismatch")
    cleaned = {
        str(game_id): value
        for game_id, value in games.items()
        if str(game_id).strip() and isinstance(value, dict)
    }
    return cleaned, payload.get("generated_at")


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


def normalize_search(value):
    decomposed = unicodedata.normalize("NFD", str(value or ""))
    asciiish = "".join(char for char in decomposed if not unicodedata.combining(char)).lower()
    return re.sub(r"\s+", " ", SEARCH_CLEAN_RE.sub(" ", asciiish)).strip()


def game_tags(game):
    value = game.get("genres", game.get("genre", []))
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").split(",")
    return [str(item).strip() for item in raw if str(item).strip()]


def metadata_tags(game):
    metadata = game.get("verified_metadata") if isinstance(game.get("verified_metadata"), dict) else {}
    value = metadata.get("genres") if isinstance(metadata.get("genres"), list) else []
    return [str(item).strip() for item in value if str(item).strip()]


def search_tokens(game):
    metadata = game.get("verified_metadata") if isinstance(game.get("verified_metadata"), dict) else {}
    text = normalize_search(
        " ".join(
            [
                str(game.get("title") or ""),
                str(metadata.get("canonical_title") or ""),
                *game_tags(game),
                *metadata_tags(game),
            ]
        )
    )
    return list(dict.fromkeys(token for token in text.split(" ") if token))


def add_posting(index, key, ordinal):
    if not key:
        return
    bucket = index.setdefault(key, [])
    if not bucket or bucket[-1] != ordinal:
        bucket.append(ordinal)


def index_game(prefixes, grams, game, ordinal):
    for token in search_tokens(game):
        for length in range(SEARCH_PREFIX_MIN, min(SEARCH_PREFIX_MAX, len(token)) + 1):
            add_posting(prefixes, token[:length], ordinal)
        if len(token) >= SEARCH_GRAM_SIZE:
            seen = set()
            for offset in range(len(token) - SEARCH_GRAM_SIZE + 1):
                gram = token[offset : offset + SEARCH_GRAM_SIZE]
                if gram in seen:
                    continue
                seen.add(gram)
                add_posting(grams, gram, ordinal)


def main():
    args = parse_args()
    source_payload = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(source_payload, dict) or not isinstance(source_payload.get("games"), list):
        raise RuntimeError("source catalog must be an object with games: []")

    metadata_path = args.metadata or args.source.with_name(METADATA_FILENAME)
    public_metadata, metadata_generated_at = load_public_metadata(metadata_path)

    data_dir = args.site_root / "data"
    details_dir = data_dir / DETAILS_DIRNAME
    catalog_path = data_dir / CATALOG_FILENAME
    search_index_path = data_dir / SEARCH_INDEX_FILENAME
    health_path = data_dir / HEALTH_FILENAME
    data_dir.mkdir(parents=True, exist_ok=True)
    if details_dir.exists():
        shutil.rmtree(details_dir)
    details_dir.mkdir(parents=True, exist_ok=True)

    catalog_games = []
    search_prefixes = {}
    search_grams = {}
    filenames = set()
    used_metadata_ids = set()
    stats = {
        "total_games": 0,
        "details_ready": 0,
        "with_description": 0,
        "with_gallery": 0,
        "with_gif": 0,
        "media_items": 0,
        "enrichment_pending": 0,
        "metadata_verified": 0,
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

        verified_metadata = public_metadata.get(game_id)
        detail_game = dict(game)
        if verified_metadata:
            detail_game["verified_metadata"] = verified_metadata
            used_metadata_ids.add(game_id)

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
            "metadata_ready": bool(verified_metadata),
            "canonical_title": verified_metadata.get("canonical_title") if verified_metadata else None,
            "game_release_date": verified_metadata.get("release_date") if verified_metadata else None,
            "metadata_genres": verified_metadata.get("genres", []) if verified_metadata else [],
            "detail_updated_at": newest_iso(
                game.get("details_checked_at"),
                game.get("media_checked_at"),
                verified_metadata.get("checked_at") if verified_metadata else None,
            ),
        })
        ordinal = len(catalog_games)
        catalog_games.append(light)
        index_game(search_prefixes, search_grams, detail_game, ordinal)
        compact_dump(details_dir / filename, detail_game)

        stats["total_games"] += 1
        stats["details_ready"] += int(details_ready)
        stats["with_description"] += int(bool(description))
        stats["with_gallery"] += int(media_count > 0)
        stats["with_gif"] += int(has_gif)
        stats["media_items"] += media_count
        stats["enrichment_pending"] += int(pending)
        stats["metadata_verified"] += int(bool(verified_metadata))

    generated_at = source_payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    catalog_payload = {
        "catalog_version": source_payload.get("catalog_version"),
        "generated_at": generated_at,
        "metadata_generated_at": metadata_generated_at,
        "count": len(catalog_games),
        "games": catalog_games,
    }
    compact_dump(catalog_path, catalog_payload)

    search_index_payload = {
        "search_index_version": SEARCH_INDEX_VERSION,
        "generated_at": generated_at,
        "metadata_generated_at": metadata_generated_at,
        "count": len(catalog_games),
        "prefix_min": SEARCH_PREFIX_MIN,
        "prefix_max": SEARCH_PREFIX_MAX,
        "gram_size": SEARCH_GRAM_SIZE,
        "prefixes": search_prefixes,
        "grams": search_grams,
    }
    compact_dump(search_index_path, search_index_payload)

    total = max(1, stats["total_games"])
    health_payload = {
        "generated_at": generated_at,
        "metadata_generated_at": metadata_generated_at,
        **stats,
        "metadata_snapshot_count": len(public_metadata),
        "metadata_unmatched": len(public_metadata) - len(used_metadata_ids),
        "coverage": {
            "details": round(stats["details_ready"] * 100 / total, 1),
            "descriptions": round(stats["with_description"] * 100 / total, 1),
            "galleries": round(stats["with_gallery"] * 100 / total, 1),
            "gifs": round(stats["with_gif"] * 100 / total, 1),
            "metadata": round(stats["metadata_verified"] * 100 / total, 1),
        },
        "expected_versions": {
            "details": EXPECTED_DETAILS_VERSION,
            "media": EXPECTED_MEDIA_VERSION,
            "metadata": EXPECTED_METADATA_VERSION,
        },
    }
    compact_dump(health_path, health_payload)

    source_bytes = args.source.stat().st_size
    catalog_bytes = catalog_path.stat().st_size
    search_bytes = search_index_path.stat().st_size
    ratio = (catalog_bytes / source_bytes) if source_bytes else 0
    print(
        f"site data built: {len(catalog_games)} games; "
        f"catalog={catalog_bytes / 1024:.1f} KiB; search-index={search_bytes / 1024:.1f} KiB; "
        f"source={source_bytes / 1024:.1f} KiB; ratio={ratio:.3f}"
    )
    print(
        "catalog health: "
        f"descriptions={stats['with_description']}/{stats['total_games']}; "
        f"galleries={stats['with_gallery']}/{stats['total_games']}; "
        f"gifs={stats['with_gif']}/{stats['total_games']}; "
        f"metadata={stats['metadata_verified']}/{stats['total_games']}; "
        f"pending={stats['enrichment_pending']}"
    )


if __name__ == "__main__":
    main()
