#!/usr/bin/env python3
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CATALOG_VERSION = 2
CURRENT_MEDIA_VERSION = 2
META_LABEL_RE = re.compile(r"\b(?:Company|Companies|Languages|Original Size|Repack Size):", re.IGNORECASE)
P = Path("site/data/games.json")
data = json.loads(P.read_text(encoding="utf-8"))

assert isinstance(data, dict), "games.json must be an object"
assert data.get("catalog_version") == CATALOG_VERSION, f"unexpected catalog_version: {data.get('catalog_version')}"
assert isinstance(data.get("games"), list), "games.json must contain games: []"
if data.get("generated_at"):
    datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))

seen = set()
for i, game in enumerate(data["games"]):
    assert isinstance(game, dict), f"game[{i}] is not an object"
    for key in ("id", "title", "source_url"):
        assert isinstance(game.get(key), str) and game[key].strip(), f"game[{i}] missing {key}"

    assert game["id"] not in seen, f"duplicate id: {game['id']}"
    seen.add(game["id"])

    source = urlparse(game["source_url"])
    assert source.scheme == "https" and (source.netloc == "fitgirl-repacks.site" or source.netloc.endswith(".fitgirl-repacks.site")), f"invalid source_url: {game['source_url']}"

    image = game.get("image_url") or ""
    if image:
        parsed_image = urlparse(image)
        assert parsed_image.scheme == "https" and parsed_image.netloc, f"invalid image_url: {image}"

    serialized = json.dumps(game, ensure_ascii=False).lower()
    assert "magnet:" not in serialized, f"magnet URI found in {game['id']}"
    assert not any(key in game for key in ("magnets", "downloads", "download_mirrors", "torrent_links")), f"forbidden download field in {game['id']}"

    if game.get("post_date"):
        datetime.fromisoformat(game["post_date"].replace("Z", "+00:00"))
    if game.get("media_checked_at"):
        datetime.fromisoformat(game["media_checked_at"].replace("Z", "+00:00"))

    genres = game.get("genres", [])
    assert isinstance(genres, list), f"genres must be list: {game['id']}"
    for genre in genres:
        assert isinstance(genre, str) and genre.strip(), f"invalid genre in {game['id']}"
        assert not META_LABEL_RE.search(genre), f"metadata leaked into genre for {game['id']}: {genre}"

    media = game.get("media", [])
    assert isinstance(media, list), f"media must be list: {game['id']}"
    media_version = game.get("media_version")
    if media_version is not None:
        assert media_version == CURRENT_MEDIA_VERSION, f"unexpected media_version in {game['id']}: {media_version}"
        assert len(media) <= 8, f"too many v{CURRENT_MEDIA_VERSION} media entries in {game['id']}"
    else:
        # Legacy v1 entries are accepted temporarily while the v2 robot replaces them in batches.
        assert len(media) <= 12, f"too many legacy media entries in {game['id']}"

    media_seen = set()
    for item in media:
        assert isinstance(item, dict), f"invalid media object in {game['id']}"
        assert item.get("type") in ("image", "gif"), f"invalid media type in {game['id']}"
        url = item.get("url")
        assert isinstance(url, str) and url.startswith("https://"), f"invalid media URL in {game['id']}"
        parsed = urlparse(url)
        assert parsed.netloc, f"invalid media host in {game['id']}"
        assert url not in media_seen, f"duplicate media URL in {game['id']}"
        media_seen.add(url)

print(f"catalog OK v{CATALOG_VERSION}: {len(data['games'])} games, {len(seen)} unique ids")
