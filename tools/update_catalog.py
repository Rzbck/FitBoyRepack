#!/usr/bin/env python3
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://fitgirl-repacks.site"
OUTPUT = Path("site/data/games.json")
CATALOG_VERSION = 2
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackCatalog/2.0)",
    "Accept-Language": "en-US,en;q=0.8",
}
SIZE_RE = re.compile(r"Repack Size:\s*(?:from\s*)?([\d.,]+\s*(?:KB|MB|GB|TB))", re.IGNORECASE)
META_LABEL_RE = re.compile(r"\b(?:Company|Companies|Languages|Original Size|Repack Size):", re.IGNORECASE)
MAX_WORKERS = 6
MAX_RETRIES = 3


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh the public metadata catalog.")
    parser.add_argument("--pages", type=int, default=6, help="Newest listing pages to scan after bootstrap.")
    parser.add_argument("--bootstrap-pages", type=int, default=300, help="Pages scanned for an empty/outdated catalog.")
    parser.add_argument("--limit", type=int, default=2500)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def load_existing():
    if not OUTPUT.exists():
        return {"catalog_version": None, "generated_at": None, "games": []}
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"catalog_version": None, "generated_at": None, "games": payload}
    return payload


def post_id(url):
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def image_url(tag):
    if not tag:
        return ""
    for key in ("data-lazy-src", "data-src", "src"):
        value = tag.get(key)
        if value and not value.startswith("data:"):
            return value.replace("http://", "https://")
    return ""


def extract_genres(article):
    """Extract only the Genres/Tags field, stopping before the next metadata line."""
    for paragraph in article.find_all("p"):
        html = str(paragraph)
        marker = html.lower().find("genres/tags:")
        if marker == -1:
            continue

        tail = html[marker + len("Genres/Tags:") :]
        # FitGirl places the next metadata field after a <br>; keep only this field.
        tail = re.split(r"<br\s*/?>", tail, maxsplit=1, flags=re.IGNORECASE)[0]
        tail = re.sub(r"^\s*</(?:strong|b)>\s*", "", tail, flags=re.IGNORECASE)
        text = BeautifulSoup(tail, "lxml").get_text(" ", strip=True)
        # Defensive fallback if the markup changes and the <br> disappears.
        text = META_LABEL_RE.split(text, maxsplit=1)[0].strip()
        return [item.strip() for item in text.split(",") if item.strip()]
    return []


def parse_article(article):
    link = article.select_one("h1.entry-title a, h2.entry-title a")
    if not link or not link.get("href"):
        return None
    title = link.get_text(" ", strip=True)
    if not title or "Updates Digest" in title or "Upcoming Repacks" in title:
        return None

    source = link["href"].replace("http://", "https://")
    size_match = SIZE_RE.search(article.get_text(" ", strip=True))
    time_tag = article.find("time")
    return {
        "id": post_id(source),
        "title": title,
        "source_url": source,
        "image_url": image_url(article.find("img")),
        "post_date": time_tag.get("datetime") if time_tag else None,
        "genres": extract_genres(article),
        "repack_size": size_match.group(1).replace(",", ".") if size_match else "N/A",
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
                time.sleep(0.6 * attempt)
    raise last_error


def discover_total_pages(client):
    html = request_text(client, BASE_URL)
    soup = BeautifulSoup(html, "lxml")
    numbers = []
    for tag in soup.select("a.page-numbers"):
        text = tag.get_text(strip=True)
        if text.isdigit():
            numbers.append(int(text))
    return max(numbers) if numbers else 1


def fetch_page(client, page):
    url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
    html = request_text(client, url)
    articles = BeautifulSoup(html, "lxml").find_all("article")
    games = []
    for article in articles:
        game = parse_article(article)
        if game:
            games.append(game)
    return page, games


def scan_pages(client, pages):
    total_pages = discover_total_pages(client)
    requested = min(max(1, pages), total_pages)
    print(f"source pages: {total_pages}; scanning: {requested}; workers: {MAX_WORKERS}")

    found = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_page, client, page) for page in range(1, requested + 1)]
        for future in as_completed(futures):
            page, games = future.result()
            print(f"page {page}: {len(games)} games")
            for game in games:
                found[game["id"]] = game
    return list(found.values())


def main():
    args = parse_args()
    current = load_existing()
    old_games = current.get("games", [])
    needs_rebuild = current.get("catalog_version") != CATALOG_VERSION

    if not old_games:
        mode = "bootstrap"
    elif needs_rebuild:
        mode = "schema-rebuild"
    else:
        mode = "incremental"

    requested_pages = max(args.pages, args.bootstrap_pages) if mode != "incremental" else args.pages
    print(f"mode: {mode}; catalog schema: {CATALOG_VERSION}")

    with httpx.Client(
        headers=HEADERS,
        timeout=httpx.Timeout(25.0, connect=15.0),
        limits=httpx.Limits(max_connections=MAX_WORKERS + 2, max_keepalive_connections=MAX_WORKERS),
        follow_redirects=True,
        http2=True,
    ) as client:
        fresh = scan_pages(client, requested_pages)

    replace = args.replace or needs_rebuild
    merged = {} if replace else {str(game.get("id")): game for game in old_games if game.get("id")}
    for game in fresh:
        merged[game["id"]] = {**merged.get(game["id"], {}), **game}
    games = sorted(merged.values(), key=lambda game: game.get("post_date") or "", reverse=True)[: max(1, args.limit)]

    if games == old_games and not needs_rebuild:
        print(f"No catalog changes ({len(games)} games).")
        return

    payload = {
        "catalog_version": CATALOG_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "games": games,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalog updated: {len(old_games)} -> {len(games)} ({len(fresh)} scanned).")


if __name__ == "__main__":
    main()
