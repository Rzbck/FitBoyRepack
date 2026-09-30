#!/usr/bin/env python3
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

FEED_URL = "https://fitgirl-repacks.site/feed/"
CATALOG = Path("site/data/games.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackFeedWatch/1.0)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
}


def load_existing_urls():
    if not CATALOG.exists():
        return set()
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    games = payload.get("games", []) if isinstance(payload, dict) else payload
    return {
        str(game.get("source_url", "")).rstrip("/") + "/"
        for game in games
        if isinstance(game, dict) and game.get("source_url")
    }


def valid_post_url(value):
    if not value:
        return ""
    value = value.strip().replace("http://", "https://", 1)
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "fitgirl-repacks.site":
        return ""
    path = parsed.path.strip("/")
    if not path or path.startswith(("feed", "page/", "category/", "tag/", "author/")):
        return ""
    return f"https://fitgirl-repacks.site/{path}/"


def extract_links(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    links = []
    seen = set()

    for item in soup.find_all(["item", "entry"]):
        raw = ""
        link = item.find("link")
        if link:
            raw = link.get("href") or link.get_text(" ", strip=True)
        url = valid_post_url(raw)
        if url and url not in seen:
            seen.add(url)
            links.append(url)

    return links


def emit(name, value):
    print(f"{name}={value}")
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main():
    existing = load_existing_urls()
    try:
        with httpx.Client(headers=HEADERS, timeout=15.0, follow_redirects=True, http2=True) as client:
            response = client.get(FEED_URL)
            response.raise_for_status()
        links = extract_links(response.text)
        if not links:
            raise RuntimeError("feed returned no usable post links")

        new_links = [url for url in links if url not in existing]
        print(f"RSS OK: {len(links)} entries, {len(new_links)} not yet in catalog")
        for url in new_links[:10]:
            print(f"NEW {url}")
        emit("feed_ok", "true")
        emit("new_count", str(len(new_links)))
    except Exception as exc:
        # RSS is only the fast signal. The workflow still scans the first listing
        # page so Cloudflare/feed outages cannot make us miss a new game.
        print(f"RSS unavailable ({type(exc).__name__}: {exc}); using listing fallback")
        emit("feed_ok", "false")
        emit("new_count", "0")


if __name__ == "__main__":
    main()
