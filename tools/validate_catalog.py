#!/usr/bin/env python3
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SUPPORTED_CATALOG_VERSIONS = {2, 3}
META_LABEL_RE = re.compile(r"\b(?:Company|Companies|Languages|Original Size|Repack Size):", re.IGNORECASE)
P = Path("site/data/games.json")
data = json.loads(P.read_text(encoding="utf-8"))

assert isinstance(data, dict), "games.json must be an object"
assert data.get("catalog_version") in SUPPORTED_CATALOG_VERSIONS, f"unexpected catalog_version: {data.get('catalog_version')}"
assert isinstance(data.get("games"), list), "games.json must contain games: []"
if data.get("generated_at"):
    datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))

seen = set()
magnet_count = 0
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

    magnet = game.get("magnet_url") or ""
    if magnet:
        assert isinstance(magnet, str), f"magnet_url must be a string in {game['id']}"
        parsed_magnet = urlparse(magnet)
        assert parsed_magnet.scheme == "magnet", f"invalid magnet scheme in {game['id']}"
        query = parse_qs(parsed_magnet.query)
        assert any(value.startswith("urn:btih:") for value in query.get("xt", [])), f"missing BitTorrent info hash in {game['id']}"
        magnet_count += 1

    assert not any(key in game for key in ("magnets", "downloads", "download_mirrors", "torrent_links", "torrent_url")), f"unexpected download field in {game['id']}"

    if game.get("post_date"):
        datetime.fromisoformat(game["post_date"].replace("Z", "+00:00"))

    genres = game.get("genres", [])
    assert isinstance(genres, list), f"genres must be list: {game['id']}"
    for genre in genres:
        assert isinstance(genre, str) and genre.strip(), f"invalid genre in {game['id']}"
        assert not META_LABEL_RE.search(genre), f"metadata leaked into genre for {game['id']}: {genre}"

print(f"catalog OK v{data.get('catalog_version')}: {len(data['games'])} games, {len(seen)} unique ids, {magnet_count} magnets")
