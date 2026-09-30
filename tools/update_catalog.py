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
OUTPUT = Path("site/data/games.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackCatalog/1.0)",
    "Accept-Language": "en-US,en;q=0.8",
}
SIZE_RE = re.compile(r"Repack Size:\s*(?:from\s*)?([\d.,]+\s*(?:KB|MB|GB|TB))", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh the public metadata catalog.")
    parser.add_argument("--pages", type=int, default=6)
    parser.add_argument("--limit", type=int, default=2500)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def load_existing():
    if not OUTPUT.exists():
        return {"generated_at": None, "games": []}
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    return {"generated_at": None, "games": payload} if isinstance(payload, list) else payload


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
    for paragraph in article.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if "Genres/Tags:" in text:
            raw = text.split("Genres/Tags:", 1)[1]
            return [item.strip() for item in raw.split(",") if item.strip()]
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


def scan_pages(client, pages):
    found = []
    seen = set()
    for page in range(1, max(1, pages) + 1):
        url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
        response = client.get(url)
        response.raise_for_status()
        articles = BeautifulSoup(response.text, "lxml").find_all("article")
        print(f"page {page}: {len(articles)} articles")
        for article in articles:
            game = parse_article(article)
            if game and game["id"] not in seen:
                seen.add(game["id"])
                found.append(game)
    return found


def main():
    args = parse_args()
    current = load_existing()
    old_games = current.get("games", [])
    with httpx.Client(
        headers=HEADERS,
        timeout=httpx.Timeout(25.0, connect=15.0),
        follow_redirects=True,
        http2=True,
    ) as client:
        fresh = scan_pages(client, args.pages)

    merged = {} if args.replace else {str(game.get("id")): game for game in old_games if game.get("id")}
    for game in fresh:
        merged[game["id"]] = {**merged.get(game["id"], {}), **game}
    games = sorted(merged.values(), key=lambda game: game.get("post_date") or "", reverse=True)[: max(1, args.limit)]

    if games == old_games:
        print(f"No catalog changes ({len(games)} games).")
        return

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "games": games}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalog updated: {len(old_games)} -> {len(games)} ({len(fresh)} scanned).")


if __name__ == "__main__":
    main()
