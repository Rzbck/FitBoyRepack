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

from catalog_classifier import classify_record, quarantine_entry

BASE_URL = "https://fitgirl-repacks.site"
OUTPUT = Path("site/data/games.json")
QUARANTINE_OUTPUT = Path("data/catalog_quarantine.json")
CATALOG_VERSION = 2
QUARANTINE_VERSION = 1
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FitBoyRepackCatalog/2.2)",
    "Accept-Language": "en-US,en;q=0.8",
}
SIZE_RE = re.compile(r"Repack Size:\s*(?:from\s*)?([\d.,]+\s*(?:KB|MB|GB|TB))", re.IGNORECASE)
META_LABEL_RE = re.compile(r"\b(?:Company|Companies|Languages|Original Size|Repack Size):", re.IGNORECASE)
DEFAULT_WORKERS = 10
MAX_RETRIES = 3


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh the public metadata catalog.")
    parser.add_argument("--pages", type=int, default=8, help="Newest listing pages to scan in incremental mode.")
    parser.add_argument("--full-scan", action="store_true", help="Scan every currently discoverable listing page.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel listing-page workers (max 24).")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional emergency cap. 0 means unlimited and keeps the complete historical catalog.",
    )
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def load_existing():
    if not OUTPUT.exists():
        return {"catalog_version": None, "generated_at": None, "games": []}
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"catalog_version": None, "generated_at": None, "games": payload}
    return payload


def load_quarantine():
    if not QUARANTINE_OUTPUT.exists():
        return {"version": QUARANTINE_VERSION, "entries": []}
    try:
        payload = json.loads(QUARANTINE_OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": QUARANTINE_VERSION, "entries": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return {"version": QUARANTINE_VERSION, "entries": []}
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
        tail = re.split(r"<br\s*/?>", tail, maxsplit=1, flags=re.IGNORECASE)[0]
        tail = re.sub(r"^\s*</(?:strong|b)>\s*", "", tail, flags=re.IGNORECASE)
        text = BeautifulSoup(tail, "lxml").get_text(" ", strip=True)
        text = META_LABEL_RE.split(text, maxsplit=1)[0].strip()
        return [item.strip() for item in text.split(",") if item.strip()]
    return []


def parse_article(article):
    link = article.select_one("h1.entry-title a, h2.entry-title a")
    if not link or not link.get("href"):
        return None
    title = link.get_text(" ", strip=True)
    if not title:
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
    held = []
    for article in articles:
        candidate = parse_article(article)
        if not candidate:
            continue
        decision = classify_record(candidate)
        if decision["kind"] == "game":
            games.append(candidate)
        else:
            held.append(quarantine_entry(candidate, decision, "excluded-new"))
    return page, games, held


def scan_pages(client, pages, workers, full_scan=False):
    total_pages = discover_total_pages(client)
    requested = total_pages if full_scan else min(max(1, pages), total_pages)
    page_numbers = range(1, requested + 1)
    print(
        f"source pages: {total_pages}; scanning: {requested}; "
        f"full_scan={str(full_scan).lower()}; workers: {workers}"
    )

    found = {}
    held = {}
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_page, client, page): page for page in page_numbers}
        for future in as_completed(futures):
            page = futures[future]
            try:
                _, games, quarantined = future.result()
                print(f"page {page}: {len(games)} games; {len(quarantined)} held")
                for game in games:
                    found[game["id"]] = game
                for item in quarantined:
                    if item.get("id"):
                        held[item["id"]] = item
            except Exception as exc:
                failures.append(page)
                print(f"page {page}: ERROR {type(exc).__name__}: {exc}")

    if requested and len(failures) == requested:
        raise RuntimeError("all requested listing pages failed")
    if failures:
        print(f"listing page failures: {len(failures)}/{requested}: {sorted(failures)}")
    return list(found.values()), list(held.values()), total_pages, failures


def merge_quarantine(previous, detections, accepted_ids):
    entries = {
        str(item.get("id")): item
        for item in previous.get("entries", [])
        if isinstance(item, dict) and item.get("id")
    }

    for game_id in accepted_ids:
        entries.pop(str(game_id), None)

    for item in detections:
        game_id = str(item.get("id") or "")
        if game_id:
            entries[game_id] = item

    ordered = sorted(
        entries.values(),
        key=lambda item: (
            item.get("classification") or "",
            item.get("title") or "",
            item.get("id") or "",
        ),
    )
    return {"version": QUARANTINE_VERSION, "entries": ordered}


def write_json_if_changed(path, payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def main():
    args = parse_args()
    current = load_existing()
    previous_quarantine = load_quarantine()
    old_games = current.get("games", [])
    needs_rebuild = current.get("catalog_version") != CATALOG_VERSION

    if not old_games:
        mode = "bootstrap"
    elif needs_rebuild:
        mode = "schema-rebuild"
    elif args.full_scan:
        mode = "full-scan"
    else:
        mode = "incremental"

    full_scan = args.full_scan or mode in {"bootstrap", "schema-rebuild"}
    workers = max(1, min(args.workers, 24))
    print(f"mode: {mode}; catalog schema: {CATALOG_VERSION}; existing games: {len(old_games)}")

    with httpx.Client(
        headers=HEADERS,
        timeout=httpx.Timeout(25.0, connect=15.0),
        limits=httpx.Limits(max_connections=workers + 2, max_keepalive_connections=workers),
        follow_redirects=True,
        http2=True,
    ) as client:
        fresh, fresh_held, total_pages, failures = scan_pages(
            client, args.pages, workers, full_scan=full_scan
        )

    detections = list(fresh_held)
    accepted_ids = {game["id"] for game in fresh if game.get("id")}
    merged = {}

    removed_existing = 0
    review_retained = 0
    for game in old_games:
        game_id = str(game.get("id") or "")
        if not game_id:
            continue
        decision = classify_record(game)
        if decision["kind"] == "non_game":
            detections.append(quarantine_entry(game, decision, "removed-existing"))
            removed_existing += 1
            continue
        if decision["kind"] == "review":
            action = "review-dropped-on-replace" if args.replace else "review-retained"
            detections.append(quarantine_entry(game, decision, action))
            review_retained += 1
            if args.replace:
                continue
        else:
            accepted_ids.add(game_id)

        if not args.replace:
            merged[game_id] = game

    for game in fresh:
        merged[game["id"]] = {**merged.get(game["id"], {}), **game}

    games = sorted(merged.values(), key=lambda game: game.get("post_date") or "", reverse=True)
    if args.limit > 0:
        games = games[: args.limit]
        print(f"WARNING: emergency catalog cap enabled: {args.limit}")

    quarantine = merge_quarantine(previous_quarantine, detections, accepted_ids)

    now = datetime.now(timezone.utc).isoformat()
    last_full_scan_at = current.get("last_full_scan_at")
    if full_scan and not failures:
        last_full_scan_at = now

    games_changed = games != old_games or needs_rebuild
    metadata_changed = (
        current.get("source_pages") != total_pages
        or current.get("last_full_scan_at") != last_full_scan_at
    )

    catalog_written = False
    if games_changed or metadata_changed:
        payload = {
            "catalog_version": CATALOG_VERSION,
            "generated_at": now,
            "source_pages": total_pages,
            "last_full_scan_at": last_full_scan_at,
            "games": games,
        }
        catalog_written = write_json_if_changed(OUTPUT, payload)

    quarantine_written = write_json_if_changed(QUARANTINE_OUTPUT, quarantine)

    if not catalog_written and not quarantine_written:
        print(
            f"No catalog/classification changes ({len(games)} games; "
            f"{len(quarantine['entries'])} quarantine entries)."
        )
        return

    print(
        f"Catalog updated: {len(old_games)} -> {len(games)} games; "
        f"{len(fresh)} accepted from scan; {len(fresh_held)} held; "
        f"{removed_existing} historical non-games removed; "
        f"{review_retained} historical low-signal records reviewed; "
        f"source pages={total_pages}; failures={len(failures)}."
    )
    print(f"Quarantine entries: {len(quarantine['entries'])}")


if __name__ == "__main__":
    main()
