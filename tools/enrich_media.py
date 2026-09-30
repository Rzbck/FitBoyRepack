#!/usr/bin/env python3
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

CATALOG = Path("site/data/games.json")
MAX_WORKERS = 8
MAX_RETRIES = 3
MAX_MEDIA_PER_GAME = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackMedia/1.0)",
    "Accept-Language": "en-US,en;q=0.8",
}
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif)(?:$|[?#])", re.IGNORECASE)
SKIP_HINTS = ("logo", "avatar", "emoji", "smiley", "counter", "rating", "button", "icon")


def parse_args():
    parser = argparse.ArgumentParser(description="Incrementally enrich catalog entries with public screenshots/GIFs.")
    parser.add_argument("--batch", type=int, default=180, help="Maximum games to enrich in one run.")
    parser.add_argument("--refresh", action="store_true", help="Recheck entries that already have media_checked_at.")
    return parser.parse_args()


def load_catalog():
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise RuntimeError("invalid catalog payload")
    return payload


def clean_url(base_url, value):
    if not value or value.startswith(("data:", "javascript:")):
        return ""
    url = urljoin(base_url, value.strip()).replace("http://", "https://", 1)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return url


def img_src(img, base_url):
    for key in ("data-lazy-src", "data-src", "src"):
        url = clean_url(base_url, img.get(key))
        if url:
            return url
    return ""


def classify_media(url):
    path = urlparse(url).path.lower()
    return "gif" if path.endswith(".gif") else "image"


def usable_image(url):
    lower = url.lower()
    if any(hint in lower for hint in SKIP_HINTS):
        return False
    return bool(IMAGE_EXT_RE.search(url))


def extract_media(html, source_url, cover_url):
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return []

    cover = (cover_url or "").split("?", 1)[0]
    media = []
    seen = set()
    for img in content.find_all("img"):
        source = img_src(img, source_url)
        parent = img.find_parent("a", href=True)
        linked = clean_url(source_url, parent.get("href")) if parent else ""

        candidates = []
        if linked and usable_image(linked):
            candidates.append(linked)
        if source and usable_image(source):
            candidates.append(source)

        for candidate in candidates:
            identity = candidate.split("?", 1)[0]
            if not identity or identity == cover or identity in seen:
                continue
            seen.add(identity)
            media.append({"url": candidate, "type": classify_media(candidate)})
            break

        if len(media) >= MAX_MEDIA_PER_GAME:
            break
    return media


def request_text(client, url):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(0.5 * attempt)
    raise last_error


def enrich_one(client, game):
    html = request_text(client, game["source_url"])
    return game["id"], extract_media(html, game["source_url"], game.get("image_url"))


def main():
    args = parse_args()
    payload = load_catalog()
    games = payload["games"]

    candidates = [game for game in games if game.get("source_url") and (args.refresh or not game.get("media_checked_at"))]
    candidates.sort(key=lambda game: game.get("post_date") or "", reverse=True)
    candidates = candidates[: max(1, args.batch)]
    if not candidates:
        print("No media enrichment work needed.")
        return

    print(f"media candidates: {len(candidates)}; workers: {MAX_WORKERS}")
    updates = {}
    failures = 0
    with httpx.Client(
        headers=HEADERS,
        timeout=httpx.Timeout(25.0, connect=15.0),
        limits=httpx.Limits(max_connections=MAX_WORKERS + 2, max_keepalive_connections=MAX_WORKERS),
        follow_redirects=True,
        http2=True,
    ) as client:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(enrich_one, client, game): game["id"] for game in candidates}
            for future in as_completed(futures):
                game_id = futures[future]
                try:
                    _, media = future.result()
                    updates[game_id] = media
                    print(f"{game_id}: {len(media)} media")
                except Exception as exc:
                    failures += 1
                    print(f"{game_id}: ERROR {type(exc).__name__}: {exc}")

    if not updates:
        print(f"No successful media updates; failures={failures}")
        return

    checked_at = datetime.now(timezone.utc).isoformat()
    changed = 0
    for game in games:
        if game.get("id") not in updates:
            continue
        new_media = updates[game["id"]]
        if game.get("media") != new_media or not game.get("media_checked_at"):
            game["media"] = new_media
            game["media_checked_at"] = checked_at
            changed += 1

    if not changed:
        print("Media data unchanged.")
        return

    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    CATALOG.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Media enrichment updated {changed} games; failures={failures}.")


if __name__ == "__main__":
    main()
