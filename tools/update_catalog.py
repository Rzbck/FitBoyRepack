#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://fitgirl-repacks.site"
OUTPUT = Path("data/games.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepacksCatalog/1.0; +https://github.com/Rzbck/FitBoyRepack)",
    "Accept-Language": "en-US,en;q=0.8",
}
SIZE_RE = re.compile(r"Repack Size:\s*(?:from\s*)?([\d.,]+\s*(?:KB|MB|GB|TB))", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(description="Update the FitBoyRepacks metadata catalog.")
    parser.add_argument("--pages", type=int, default=6, help="Newest listing pages to scan.")
    parser.add_argument("--limit", type=int, default=2500, help="Maximum games kept after merge.")
    parser.add_argument("--replace", action="store_true", help="Replace instead of merging with existing JSON.")
    return parser.parse_args()


def load_existing():
    if not OUTPUT.exists():
        return {"generated_at": None, "games": []}
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"generated_at": None, "games": payload}
    return payload


def post_id(url):
    path = urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1]


def normalize_image(tag):
    if not tag:
        return ""
    for key in ("data-lazy-src", "data-src", "src"):
        value = tag.get(key)
        if value and not value.startswith("data:"):
            return value.replace("http://", "https://")
    return ""


def extract_genres(article):
    for paragraph in article.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if "Genres/Tags:" in text:
            raw = text.split("Genres/Tags:", 1)[1]
            return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def parse_article(article):
    title_link = article.select_one("h1.entry-title a, h2.entry-title a")
    if not title_link or not title_link.get("href"):
        return None

    title = title_link.get_text(" ", strip=True)
    if not title or "Updates Digest" in title or "Upcoming Repacks" in title:
        return None

    source_url = title_link["href"].replace("http://", "https://")
    text = article.get_text(" ", strip=True)
    size_match = SIZE_RE.search(text)
    time_tag = article.find("time")

    return {
        "id": post_id(source_url),
        "title": title,
        "image_url": normalize_image(article.find("img")),
        "post_date": time_tag.get("datetime") if time_tag else None,
        "genres": extract_genres(article),
        "repack_size": size_match.group(1).replace(",", ".") if size_match else "N/A",
    }


def scan_pages(client, pages):
    found = []
    seen = set()
    for page in range(1, max(1, pages) + 1):
        url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
        response = client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        articles = soup.find_all("article")
        print(f"page {page}: {len(articles)} articles")
        for article in articles:
            game = parse_article(article)
            if not game or game["id"] in seen:
                continue
            seen.add(game["id"])
            found.append(game)
    return found


def main():
    args = parse_args()
    existing = load_existing()
    old_games = existing.get("games", [])

    timeout = httpx.Timeout(25.0, connect=15.0)
    limits = httpx.Limits(max_keepalive_connections=4, max_connections=8)
    with httpx.Client(headers=HEADERS, timeout=timeout, limits=limits, follow_redirects=True, http2=True) as client:
        fresh = scan_pages(client, args.pages)

    if args.replace:
        merged = {game["id"]: game for game in fresh}
    else:
        merged = {str(game.get("id")): game for game in old_games if game.get("id")}
        for game in fresh:
            merged[game["id"]] = {**merged.get(game["id"], {}), **game}

    games = sorted(merged.values(), key=lambda game: game.get("post_date") or "", reverse=True)[:max(1, args.limit)]

    if games == old_games:
        print(f"No catalog changes ({len(games)} games).")
        return

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "games": games,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalog updated: {len(old_games)} -> {len(games)} games ({len(fresh)} scanned).")


if __name__ == "__main__":
    main()
