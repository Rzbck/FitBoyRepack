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
DEFAULT_WORKERS = 12
MAX_RETRIES = 3
MAX_MEDIA_PER_GAME = 8
MEDIA_VERSION = 3
DETAILS_VERSION = 1
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackDetails/3.1)",
    "Accept-Language": "en-US,en;q=0.8",
}

# FitGirl's real screenshot thumbnails use this naming convention. Generic
# entry-content images are too noisy and can include widgets or banners.
SCREENSHOT_THUMB_RE = re.compile(r"\.jpg\.240p\.jpg(?:$|[?#])", re.IGNORECASE)
GIF_RE = re.compile(r"\.gif(?:$|[?#])", re.IGNORECASE)
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp)(?:$|[?#])", re.IGNORECASE)
SKIP_HINTS = (
    "logo", "avatar", "emoji", "smiley", "counter", "rating", "button", "icon",
    "badge", "banner", "donat", "patreon", "discord", "telegram", "rss", "feed",
    "registered-users", "torrent-stats",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Incrementally enrich catalog entries with public details, screenshots and GIFs.")
    parser.add_argument("--batch", type=int, default=360, help="Maximum games to enrich in one run.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel detail-page workers (max 24).")
    parser.add_argument("--refresh", action="store_true", help="Recheck entries even when already on the current parser versions.")
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


def compact_text(value, limit=6000):
    value = re.sub(r"[ \t\r\f\v]+", " ", value or "")
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()[:limit]


def compact_lines(value, limit=40):
    lines = []
    seen = set()
    for raw in (value or "").splitlines():
        line = re.sub(r"^[\s•·▪►→⇢–—-]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if not line or line.lower() in {"game features", "repack features"}:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line[:500])
        if len(lines) >= limit:
            break
    return lines


def extract_media(html, source_url, cover_url):
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return []

    cover = normalize_identity(cover_url or "")
    media = []
    seen = set()

    # First pass: reserve the gameplay GIF before screenshots can fill the media
    # budget. The legacy site surfaced this separately as "Gameplay Preview".
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
        candidate = linked if linked and GIF_RE.search(linked) else source
        identity = normalize_identity(candidate)
        if GIF_RE.search(candidate) and identity and identity != cover:
            seen.add(identity)
            media.append({"url": candidate, "type": "gif"})
            break

    # Second pass: only the site's verified screenshot thumbnail pattern.
    for img in content.find_all("img"):
        source = img_src(img, source_url)
        if not source or not SCREENSHOT_THUMB_RE.search(source):
            continue
        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = clean_url(source_url, parent.get("href")) if parent else ""
        if has_skip_hint(source, linked, alt, classes):
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


def find_text_heading(root, needle):
    needle = needle.casefold()
    for tag in root.find_all(["h2", "h3", "h4", "strong", "div", "span"]):
        text = tag.get_text(" ", strip=True)
        if text and needle in text.casefold() and len(text) < 100:
            return tag
    return None


def extract_details(html):
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return {"description": "", "game_features": [], "repack_features": []}

    description = ""
    game_features = []
    repack_features = []

    spoiler_title = None
    for tag in content.select(".su-spoiler-title"):
        if "game description" in tag.get_text(" ", strip=True).casefold():
            spoiler_title = tag
            break

    if spoiler_title:
        spoiler_body = spoiler_title.find_next_sibling()
        if spoiler_body:
            text = spoiler_body.get_text("\n", strip=True)
            parts = re.split(r"\bGame Features\b", text, maxsplit=1, flags=re.IGNORECASE)
            description = compact_text(parts[0])
            if len(parts) > 1:
                game_features = compact_lines(parts[1])

    # Fallback for pages with a slightly different spoiler structure.
    if not description:
        heading = find_text_heading(content, "Game Description")
        if heading:
            candidate = heading.find_next_sibling()
            if candidate:
                description = compact_text(candidate.get_text("\n", strip=True))

    repack_heading = find_text_heading(content, "Repack Features")
    if repack_heading:
        candidate = repack_heading.find_next_sibling()
        if candidate:
            repack_features = compact_lines(candidate.get_text("\n", strip=True))

    return {
        "description": description,
        "game_features": game_features,
        "repack_features": repack_features,
    }


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
    return (
        game["id"],
        extract_media(html, game["source_url"], game.get("image_url")),
        extract_details(html),
    )


def main():
    args = parse_args()
    payload = load_catalog()
    games = payload["games"]
    workers = max(1, min(args.workers, 24))

    candidates = [
        game for game in games
        if game.get("source_url") and (
            args.refresh
            or game.get("media_version") != MEDIA_VERSION
            or game.get("details_version") != DETAILS_VERSION
        )
    ]
    candidates.sort(key=lambda game: game.get("post_date") or "", reverse=True)
    candidates = candidates[: max(1, args.batch)]
    if not candidates:
        print("No details/media enrichment work needed.")
        return

    print(
        f"details/media candidates: {len(candidates)}; workers: {workers}; "
        f"media=v{MEDIA_VERSION}; details=v{DETAILS_VERSION}"
    )
    updates = {}
    failures = 0
    with httpx.Client(
        headers=HEADERS,
        timeout=httpx.Timeout(25.0, connect=15.0),
        limits=httpx.Limits(max_connections=workers + 2, max_keepalive_connections=workers),
        follow_redirects=True,
        http2=True,
    ) as client:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(enrich_one, client, game): game["id"] for game in candidates}
            for future in as_completed(futures):
                game_id = futures[future]
                try:
                    _, media, details = future.result()
                    updates[game_id] = (media, details)
                    gif_count = sum(1 for item in media if item.get("type") == "gif")
                    print(
                        f"{game_id}: {len(media)} media ({gif_count} gif); "
                        f"description={'yes' if details.get('description') else 'no'}"
                    )
                except Exception as exc:
                    failures += 1
                    print(f"{game_id}: ERROR {type(exc).__name__}: {exc}")

    if not updates:
        print(f"No successful detail/media updates; failures={failures}")
        return

    checked_at = datetime.now(timezone.utc).isoformat()
    changed = 0
    for game in games:
        if game.get("id") not in updates:
            continue
        new_media, new_details = updates[game["id"]]
        if (
            game.get("media") != new_media
            or game.get("media_version") != MEDIA_VERSION
            or game.get("details") != new_details
            or game.get("details_version") != DETAILS_VERSION
            or not game.get("media_checked_at")
            or not game.get("details_checked_at")
        ):
            game["media"] = new_media
            game["media_version"] = MEDIA_VERSION
            game["media_checked_at"] = checked_at
            game["details"] = new_details
            game["details_version"] = DETAILS_VERSION
            game["details_checked_at"] = checked_at
            changed += 1

    if not changed:
        print("Details/media data unchanged.")
        return

    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    CATALOG.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Details/media enrichment updated {changed} games; failures={failures}.")


if __name__ == "__main__":
    main()
