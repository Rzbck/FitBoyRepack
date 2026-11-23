#!/usr/bin/env python3
"""Gradual, keyless Steam review enrichment for FitBoyRepack static catalog.

Only public metadata. Never scrapes download links. An ID is accepted only when
Wikidata P1733 names exactly one Steam app. Unresolved titles remain unscored.
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CATALOG = Path("site/data/games.json")
METADATA = Path("site/data/metadata-enrichment.json")
OUTPUT = Path("site/data/steam-ratings.json")
WIKIDATA = "https://www.wikidata.org/w/api.php"
STEAM = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
STEAM_STORE = "https://store.steampowered.com/api/appdetails"
STEAM_SEARCH = "https://store.steampowered.com/api/storesearch"
STORE_LOOKUP_AGE_DAYS = 14
STORE_VERIFY_AGE_DAYS = 28
STORE_DETAILS_LIMIT = 160
STORE_FALLBACK_LIMIT = 20
STORE_AUDIT_LIMIT = 35
USER_AGENT = "FitBoyRepack-SteamReviews/1.0 (https://github.com/Rzbck/FitBoyRepack; keyless public metadata research)"
QID_RE = re.compile(r"^https?://(?:www\.)?wikidata\.org/(?:wiki/|entity/)(Q[1-9]\d*)/?$")
APP_ID_RE = re.compile(r"^[1-9]\d{0,9}$")
LOGGER = logging.getLogger("steam_ratings")


class Cooldown(Exception):
    """A provider asked the bot to stop. Save current progress and exit."""


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def days_since(value, now):
    try:
        if not value:
            return 99999
        return (now - datetime.fromisoformat(value.replace("Z", "+00:00"))).total_seconds() / 86400
    except (ValueError, TypeError):
        return 99999


def get_json(url, params, pause=0):
    if pause:
        time.sleep(pause)
    url += "?" + urlencode(params)
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        with urlopen(request, timeout=28) as response:
            body = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
            parsed = json.loads(body.decode("utf-8"))
            error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
            code = str(error.get("code", "")).lower() if isinstance(error, dict) else ""
            if code in ("maxlag", "ratelimited", "readonly", "readonlytext"):
                raise Cooldown(f"Provider requested slowdown ({code})")
            return parsed
    except HTTPError as error:
        if error.code in (403, 429, 503):
            retry = error.headers.get("Retry-After", "not specified")
            raise Cooldown(f"HTTP {error.code} from {url.split('?')[0]}; Retry-After: {retry}") from error
        raise


def qid_from_metadata(meta):
    if not isinstance(meta, dict):
        return None
    for url in meta.get("evidence_urls", []):
        match = QID_RE.fullmatch(str(url).strip())
        if match:
            return match.group(1)
    return None


def steam_id_from_entity(entity):
    claims = entity.get("claims", {}).get("P1733", [])
    values = set()
    for claim in claims:
        if claim.get("rank") == "deprecated":
            continue
        raw = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        value = str(raw).strip()
        if APP_ID_RE.fullmatch(value):
            values.add(int(value))
    return next(iter(values)) if len(values) == 1 else None


def wikidata_with_retry(url, params, pause=0, attempts=3):
    """Bounded, non-destructive retries after Wikidata maxlag/429/503."""
    for attempt in range(attempts):
        try:
            return get_json(url, params, pause=pause)
        except Cooldown as error:
            if attempt + 1 == attempts:
                raise
            delay = (4, 10)[min(attempt, 1)]
            LOGGER.warning("Wikidata backoff %ss after %s (attempt %s/%s)",
                           delay, error, attempt + 1, attempts)
            time.sleep(delay)


def wikidata_entities(ids):
    if not ids:
        return {}
    # Query only the exact P1733 properties we need, rather than downloading
    # complete entities. This is Wikidata's recommended use case for SPARQL.
    query = "SELECT ?item ?steam WHERE { VALUES ?item { " + " ".join("wd:" + q for q in ids) + " } ?item wdt:P1733 ?steam }"
    try:
        sparql = get_json("https://query.wikidata.org/sparql",
                          {"query": query, "format": "json"}, pause=2.0)
        bindings = sparql.get("results", {}).get("bindings")
        if not isinstance(bindings, list):
            raise ValueError("Unexpected Wikidata SPARQL response")
    except (Cooldown, HTTPError, URLError, ValueError) as error:
        LOGGER.warning("Wikidata SPARQL unavailable (%s); trying bounded Action API", error)
        response = wikidata_with_retry(WIKIDATA, {
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "claims",
            "format": "json",
            "maxlag": "5",
        }, pause=1.5)
        if not isinstance(response.get("entities"), dict):
            raise ValueError("Unexpected Wikidata entity response")
        return response["entities"]
    out = {}
    for row in bindings:
        qid = str(row.get("item", {}).get("value", "")).rsplit("/", 1)[-1]
        appid = str(row.get("steam", {}).get("value", ""))
        if qid in ids and APP_ID_RE.fullmatch(appid):
            out.setdefault(qid, {"claims": {"P1733": []}})["claims"]["P1733"].append(
                {"mainsnak": {"datavalue": {"value": appid}}})
    return out


def clean_title(text):
    text = str(text or "").strip()
    # Strip repack release suffix, not meaningful title words.
    text = re.split(r"\s+[–—-]\s+(?=v\d|build\b|update\b|repack\b)", text, maxsplit=1, flags=re.I)[0]
    return text.strip()


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "").casefold())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", "".join(c for c in text if not unicodedata.combining(c)))).strip()



def title_variants(text):
    """Strict name identities: editions/build tags may vary, sequels must not."""
    raw = clean_title(text)
    raw = re.split(r",\s*(?=v\d|build\b|update\b)", raw, maxsplit=1, flags=re.I)[0]
    variants = {normalize(raw)}
    edition = (
        r"(?:[:\s-]+)(?:gold|deluxe|ultimate|complete|standard|premium|"
        r"definitive|anniversary|special|enhanced|legendary|collector'?s|"
        r"game of the year|goty)\s+edition$"
    )
    base = re.sub(edition, "", raw, flags=re.I).strip()
    if base:
        variants.add(normalize(base))
    # Steam Store titles do not contain "PC" or console release packaging.
    for platform in (r"\s+\(PC\)$", r"\s+\(Switch\)$", r"\s+-\s+PC$"):
        candidate = re.sub(platform, "", base, flags=re.I).strip()
        if candidate:
            variants.add(normalize(candidate))
    return {value for value in variants if value}


def game_title_variants(game, metadata=None):
    raw = title_variants(game.get("title", ""))
    canonical = (metadata or {}).get("canonical_title", "")
    # Metadata may refer to a *different sequel*. Do not trust a QID alone.
    extra = title_variants(canonical) if canonical else set()
    return raw | extra if raw & extra else raw


def store_game_title(game, metadata=None):
    candidates = [
        re.sub(r"(?:[:\s-]+)(?:gold|deluxe|ultimate|complete|standard|"
               r"premium|definitive|anniversary|special|enhanced|legendary|"
               r"collector'?s|game of the year|goty)\s+edition$", "",
               clean_title(game.get("title", "")).split(", v")[0], flags=re.I).strip(),
    ]
    canonical = (metadata or {}).get("canonical_title", "")
    if canonical and game_title_variants(game, metadata) & title_variants(canonical):
        candidates.append(canonical)
    return next((name for name in candidates if 3 <= len(name) <= 110), "")


def store_details(appid, pause=1.5):
    response = get_json(STEAM_STORE, {
        "appids": int(appid), "cc": "us", "l": "en", "filters": "basic"
    }, pause=pause)
    item = response.get(str(appid), {})
    if item.get("success") is not True or not isinstance(item.get("data"), dict):
        raise ValueError("Steam Store did not return public app details")
    data = item["data"]
    name = str(data.get("name") or "").strip()
    kind = str(data.get("type") or "").lower()
    if not name or not kind:
        raise ValueError("Steam Store app details missing name/type")
    return {"name": name, "type": kind}


def store_verified(game, metadata, details):
    return (details.get("type") == "game"
            and normalize(details.get("name")) in game_title_variants(game, metadata))


def exact_store_search(game, metadata, pause=1.5):
    title = store_game_title(game, metadata)
    if not title:
        return None
    response = get_json(STEAM_SEARCH,
                        {"term": title, "l": "en", "cc": "us"}, pause=pause)
    keys = game_title_variants(game, metadata)
    items = response.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Unexpected Steam Store search response")
    exact_ids = set()
    for item in items:
        try:
            appid = int(item["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if appid > 0 and normalize(item.get("name")) in keys:
            exact_ids.add(appid)
    # Ambiguity is safer than assigning the score of an unrelated game.
    return next(iter(exact_ids)) if len(exact_ids) == 1 else None


def invalidate_match(record, reason):
    """Hide an incorrect app's review score, retaining evidence for diagnosis."""
    record["invalid_steam_appid"] = record.pop("steam_appid", None)
    for key in ("positive", "negative", "positive_percent", "total_reviews",
                "review_checked_at", "store_verified_at", "steam_store_name"):
        record.pop(key, None)
    record["status"] = "mismatch"
    record["identity_issue"] = reason
    record["lookup_checked_at"] = iso(utc_now())


def exact_title_entity(title):
    if not title or len(title) < 4 or len(title) > 90:
        return None
    response = get_json(WIKIDATA, {
        "action": "wbsearchentities",
        "search": title,
        "language": "en",
        "limit": "8",
        "format": "json",
        "maxlag": "5",
    }, pause=1.5)
    target = normalize(title)
    exact = [item["id"] for item in response.get("search", []) if normalize(item.get("label")) == target and re.fullmatch(r"Q[1-9]\d*", item.get("id", ""))]
    if len(exact) != 1:
        return None
    qid = exact[0]
    entity = wikidata_entities([qid]).get(qid, {})
    appid = steam_id_from_entity(entity)
    return (qid, appid) if appid else None


def load_source():
    source = json.loads(CATALOG.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if not isinstance(source.get("games"), list) or metadata.get("metadata_version") != 1:
        raise ValueError("Unexpected catalog or verified metadata format")
    return [g for g in source["games"] if isinstance(g, dict) and g.get("id") and g.get("title")], metadata.get("games", {})


def load_state():
    if not OUTPUT.exists():
        return {"rating_version": 1, "generated_at": None, "games": {}}
    state = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if state.get("rating_version") != 1 or not isinstance(state.get("games"), dict):
        raise ValueError("Invalid reviews cache. Refusing to overwrite.")
    return state


def eligible_to_resolve(row, qid, now):
    if row is None:
        return True
    if row.get("wikidata_id") != qid:
        return True
    return row.get("status") == "no_match" and days_since(row.get("lookup_checked_at"), now) >= 60


def collect_steam_reviews(appid, pause):
    response = get_json(STEAM, {
        "input_json": json.dumps({
            "appid": int(appid),
            "num_per_page": 1,
            "review_type": 0,
            "purchase_type": 1,
        }, separators=(",", ":")),
    }, pause=pause)
    summary = response.get("response", {}).get("query_summary")
    if not isinstance(summary, dict):
        raise ValueError("Steam returned no query_summary")
    positive = int(summary.get("total_positive", -1))
    negative = int(summary.get("total_negative", -1))
    total = int(summary.get("total_reviews", -1))
    if positive < 0 or negative < 0 or total < 0 or positive + negative > total:
        raise ValueError("Inconsistent Steam review counts")
    return {
        "status": "rated" if total > 0 else "no_reviews",
        "positive": positive,
        "negative": negative,
        "total_reviews": total,
        "positive_percent": round(100 * positive / total, 1) if total else None,
        "review_checked_at": iso(utc_now()),
    }


def update(args):
    now = utc_now()
    games, metadata = load_source()
    state = load_state()
    records = state["games"]
    current_ids = {str(game["id"]) for game in games}
    for obsolete in set(records) - current_ids:
        del records[obsolete]
    changes = 0

    games.sort(key=lambda game: str(game.get("post_date", "")), reverse=True)
    by_id = {str(game["id"]): game for game in games}
    known_qids = {}
    for game_id, game in by_id.items():
        qid = qid_from_metadata(metadata.get(game_id))
        if qid:
            known_qids[game_id] = qid

    # Wikidata P1733 is only a *candidate*: Steam itself verifies name and type.
    candidates = [(game_id, qid) for game_id, qid in known_qids.items()
                  if eligible_to_resolve(records.get(game_id), qid, now)][:args.resolve_limit]
    for offset in range(0, len(candidates), 25):
        batch = candidates[offset:offset + 25]
        try:
            entities = wikidata_entities(list(dict.fromkeys(qid for _, qid in batch)))
        except Cooldown as error:
            LOGGER.warning("%s. Stopping Wikidata lookups safely.", error)
            break
        except (HTTPError, URLError, ValueError) as error:
            LOGGER.warning("Wikidata unavailable; preserving progress: %s", error)
            break
        for game_id, qid in batch:
            appid = steam_id_from_entity(entities.get(qid, {}))
            old = records.get(game_id, {})
            if appid:
                records[game_id] = {
                    **(old if old.get("steam_appid") == appid else {}),
                    "wikidata_id": qid, "steam_appid": appid,
                    "resolution": "wikidata_P1733",
                    "status": old.get("status", "pending") if old.get("steam_appid") == appid else "pending",
                    "lookup_checked_at": iso(now),
                }
            else:
                records[game_id] = {"wikidata_id": qid, "status": "no_match",
                                    "lookup_checked_at": iso(now)}
            changes += 1

    # Existing exact-title Wikidata fallback, still bounded and conservative.
    fallback = [(game_id, game) for game_id, game in by_id.items()
                if game_id not in known_qids
                and days_since(records.get(game_id, {}).get("lookup_checked_at"), now) >= 60]
    for game_id, game in fallback[:args.fallback_limit]:
        title = clean_title(game.get("title"))
        try:
            result = exact_title_entity(title)
        except Cooldown as error:
            LOGGER.warning("%s. Stopping title search safely.", error)
            break
        except (HTTPError, URLError, ValueError) as error:
            LOGGER.warning("Wikidata title lookup unavailable: %s", error)
            break
        if result:
            qid, appid = result
            old = records.get(game_id, {})
            records[game_id] = {
                **(old if old.get("steam_appid") == appid else {}),
                "wikidata_id": qid, "steam_appid": appid,
                "resolution": "unique_exact_title",
                "status": old.get("status", "pending") if old.get("steam_appid") == appid else "pending",
                "lookup_checked_at": iso(now),
            }
        else:
            records[game_id] = {"status": "no_match", "lookup_checked_at": iso(now)}
        changes += 1

    # Storefront app details are authoritative for *what* the ID represents.
    store_calls = 0
    store_search_calls = 0
    store_cache = {}
    store_budget = getattr(args, "store_details_limit", STORE_DETAILS_LIMIT)

    def check_identity(game, row):
        nonlocal store_calls, changes
        if (row.get("steam_appid") and row.get("store_verified_at")
                and days_since(row["store_verified_at"], now) < STORE_VERIFY_AGE_DAYS):
            return True
        if store_calls >= store_budget:
            return None
        appid = row.get("steam_appid")
        if not appid:
            return False
        if appid not in store_cache:
            # One request per distinct app ID, shared across duplicate catalog entries.
            store_calls += 1
            store_cache[appid] = store_details(appid)
        details = store_cache[appid]
        if not store_verified(game, metadata.get(str(game["id"])), details):
            LOGGER.warning("REJECTED Steam ID %s for %s: Steam says %s (%s)",
                           appid, game["id"], details["name"], details["type"])
            invalidate_match(row, "wrong_game_or_app_type")
            changes += 1
            return False
        row["store_verified_at"] = iso(now)
        row["steam_store_name"] = details["name"]
        row.pop("identity_issue", None)
        changes += 1
        return True

    # Audit older cached scores first. Prioritize suspicious verified-metadata
    # collisions (e.g., Modern Warfare II linked to III) before regular scores.
    legacy = [game for game in games
              if records.get(str(game["id"]), {}).get("status") == "rated"
              and not records[str(game["id"])].get("store_verified_at")]
    legacy.sort(key=lambda game: (
        bool(title_variants(game.get("title")) &
             title_variants(metadata.get(str(game["id"]), {}).get("canonical_title"))),
        str(game.get("post_date", "")),
    ))
    for game in legacy[:getattr(args, "store_audit_limit", STORE_AUDIT_LIMIT)]:
        try:
            check_identity(game, records[str(game["id"])])
        except Cooldown as error:
            LOGGER.warning("Store throttled during cache audit (%s); preserving remaining scores", error)
            break
        except (HTTPError, URLError, ValueError) as error:
            LOGGER.warning("Store identity audit unavailable for %s: %s", game["id"], error)
            break

    # Secondary recovery route: exact Steam Store search, including games that
    # have a Wikidata item but no P1733. No fuzzy scores, no API keys.
    missing = [game for game in games
               if not records.get(str(game["id"]), {}).get("steam_appid")
               and days_since(records.get(str(game["id"]), {}).get("store_lookup_checked_at"), now)
                   >= STORE_LOOKUP_AGE_DAYS]
    missing.sort(key=lambda game: records.get(str(game["id"]), {}).get("status")
                 not in ("mismatch", "no_match"))
    for game in missing[:getattr(args, "store_fallback_limit", STORE_FALLBACK_LIMIT)]:
        if store_calls >= store_budget:
            break
        game_id = str(game["id"])
        row = records.setdefault(game_id, {})
        try:
            appid = exact_store_search(game, metadata.get(game_id))
            store_search_calls += 1
            if appid:
                # Store search shows only a name; validate type and identity again.
                if appid not in store_cache:
                    store_calls += 1
                    store_cache[appid] = store_details(appid)
                details = store_cache[appid]
                if store_verified(game, metadata.get(game_id), details):
                    row.update({
                        "steam_appid": appid,
                        "steam_store_name": details["name"],
                        "store_verified_at": iso(now),
                        "resolution": "steam_store_exact",
                        "status": "pending",
                    })
                    row.pop("identity_issue", None)
                else:
                    LOGGER.warning("Rejected fallback %s for %s (%s)",
                                   appid, game_id, details["name"])
                    row.setdefault("status", "no_match")
            else:
                row.setdefault("status", "no_match")
        except Cooldown as error:
            LOGGER.warning("Steam Store asked for slowdown (%s); keeping pending matches", error)
            break
        except (HTTPError, URLError, ValueError) as error:
            LOGGER.warning("Steam Store search unavailable for %s: %s", game_id, error)
            break
        row["store_lookup_checked_at"] = iso(now)
        changes += 1

    # Prefer new/unrated games. Recheck existing scores at most every 28 days.
    review_queue = [game for game in games
                    if records.get(str(game["id"]), {}).get("steam_appid")
                    and days_since(records[str(game["id"])].get("review_checked_at"), now) >= 28]
    review_queue.sort(key=lambda game: (
        bool(records[str(game["id"])].get("review_checked_at")),
        -datetime.fromisoformat(str(game.get("post_date") or "1970-01-01").replace("Z", "+00:00")).timestamp()
        if re.match(r"^\d{4}-\d\d-\d\d", str(game.get("post_date"))) else 0,
    ))
    review_cache = {}
    for row in records.values():
        appid = row.get("steam_appid")
        if appid and row.get("store_verified_at") and row.get("review_checked_at") and (
                days_since(row["review_checked_at"], now) < 28):
            review_cache[appid] = {key: row[key] for key in
                                  ("status", "positive", "negative", "total_reviews",
                                   "positive_percent", "review_checked_at") if key in row}

    attempted = 0
    for game in review_queue:
        if attempted >= args.reviews_limit:
            break
        game_id = str(game["id"])
        row = records[game_id]
        try:
            identity = check_identity(game, row)
        except Cooldown as error:
            LOGGER.warning("Store identity throttled (%s); stopping safely.", error)
            break
        except (HTTPError, URLError, ValueError) as error:
            LOGGER.warning("Store identity unavailable for %s: %s", game_id, error)
            break
        if identity is None:
            LOGGER.info("Steam Store verification budget reached; deferred remaining games")
            break
        if identity is False:
            continue
        appid = row["steam_appid"]
        if appid in review_cache:
            row.update(review_cache[appid])
            changes += 1
            continue
        try:
            review = collect_steam_reviews(appid, args.pause)
        except Cooldown as error:
            LOGGER.warning("%s. Stopping safely.", error)
            break
        except HTTPError as error:
            if error.code in (400, 404):
                LOGGER.warning("Steam app %s unavailable (%s); skipping", appid, error.code)
                row.update({"status": "unavailable", "review_checked_at": iso(utc_now())})
                changes += 1
                continue
            LOGGER.warning("Steam temporary HTTP problem for %s: %s", appid, error)
            break
        except (URLError, ValueError, TypeError) as error:
            LOGGER.warning("Review fetch failed for app %s: %s", appid, error)
            break
        row.update(review)
        review_cache[appid] = review
        attempted += 1
        changes += 1

    stats = {
        "catalog_games": len(games),
        "rated": sum(row.get("status") == "rated" for row in records.values()),
        "no_reviews": sum(row.get("status") == "no_reviews" for row in records.values()),
        "unmatched": sum(row.get("status") == "no_match" for row in records.values()),
        "mismatched": sum(row.get("status") == "mismatch" for row in records.values()),
        "pending": sum(row.get("status") == "pending" for row in records.values()),
        "steam_calls_this_run": attempted,
        "store_checks_this_run": store_calls,
        "store_searches_this_run": store_search_calls,
    }
    LOGGER.info("Steam: %s", stats)
    if not args.dry_run and changes:
        state["generated_at"] = iso(utc_now())
        state["counts"] = stats
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temp = OUTPUT.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
                        encoding="utf-8")
        temp.replace(OUTPUT)
        LOGGER.info("Saved %s updated records to %s", changes, OUTPUT)
    else:
        LOGGER.info("No write (dry-run or unchanged)")
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolve-limit", type=int, default=300)
    parser.add_argument("--reviews-limit", type=int, default=120)
    parser.add_argument("--fallback-limit", type=int, default=25)
    parser.add_argument("--pause", type=float, default=3.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.resolve_limit <= 400 or not 0 <= args.reviews_limit <= 160 or not 0 <= args.fallback_limit <= 40 or not 0 <= args.pause <= 60:
        parser.error("batch limits outside safety bounds")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    update(args)


if __name__ == "__main__":
    main()
