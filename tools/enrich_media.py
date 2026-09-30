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
MAX_MEDIA_PER_GAME = 8
MEDIA_VERSION = 2
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackMedia/2.0)",
    "Accept-Language": "en-US,en;q=0.8",
}

# FitGirl's actual screenshot thumbnails use this naming convention. The old app
# deliberately keyed off it; generic entry-content images are too noisy and can
# include unrelated widgets/text captures.
SCREENSHOT_THUMB_RE = re.compile(r"\.jpg\.240p\.jpg(?:$|[?#])", re.IGNORECASE)
GIF_RE = re.compile(r"\.gif(?:$|[?#])", re.IGNORECASE)
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp)(?:$|[?#])", re.IGNORECASE)
SKIP_HINTS = (
    "logo", "avatar", "emoji", "smiley", "counter", "rating", "button", "icon",
    "badge", "banner", "donat", "patreon", "discord", "telegram", "rss", "feed",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Incrementally enrich catalog entries with filtered public screenshots/GIFs.")
    parser.add_argument("--batch", type=int, default=180, help="Maximum games to enrich in one run.")
    parser.add_argument("--refresh", action="store_true", help="Recheck entries even when already on the current media parser version.")
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


def has_skip_hint(*values):
    lower = " ".join(value.lower() for value in values if value)
    return any(hint in lower for hint in SKIP_HINTS)


def normalize_identity(url):
    return url.split("?", 1)[0].split("#", 1)[0]


def extract_media(html, source_url, cover_url):
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return []

    cover = normalize_identity(cover_url or "")
    media = []
    seen = set()
    gif_added = False

    for img in content.find_all("img"):
        source = img_src(img, source_url)
        if not source:
            continue

        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = clean_url(source_url, parent.get("href")) if parent else ""

        if has_skip_hint(source, linked, alt, classes):
            continue

        source_id = normalize_identity(source)
        if not source_id or source_id == cover:
            continue

        # GIF: keep at most one animation, matching the behavior of the old app.
        if GIF_RE.search(source):
            candidate = linked if linked and GIF_RE.search(linked) else source
            identity = normalize_identity(candidate)
            if gif_added or identity in seen:
                continue
            seen.add(identity)
            media.append({"url": candidate, "type": "gif"})
            gif_added = True
            if len(media) >= MAX_MEDIA_PER_GAME:
                break
            continue

        # Screenshots: only accept the site's real 240p screenshot thumbnails.
        # If the thumbnail links to a full-resolution image, expose that image;
        # otherwise keep the verified thumbnail itself.
        if not SCREENSHOT_THUMB_RE.search(source):
            continue

        candidate = linked if linked and IMAGE_EXT_RE.search(linked) else source
        identity = normalize_identity(candidate)
        if not identity or identity == cover or identity in seen:
            continue

        seen.add(identity)
        media.append({"url": candidate, "type": "image"})
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

    # Parser versioning automatically revisits old/bad media after filter changes.
    candidates = [
        game for game in games
        if game.get("source_url") and (args.refresh or game.get("media_version") != MEDIA_VERSION)
    ]
    candidates.sort(key=lambda game: game.get("post_date") or "", reverse=True)
    candidates = candidates[: max(1, args.batch)]
    if not candidates:
        print("No media enrichment work needed.")
        return

    print(f"media candidates: {len(candidates)}; workers: {MAX_WORKERS}; parser=v{MEDIA_VERSION}")
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
        if (
            game.get("media") != new_media
            or game.get("media_version") != MEDIA_VERSION
            or not game.get("media_checked_at")
        ):
            game["media"] = new_media
            game["media_version"] = MEDIA_VERSION
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
