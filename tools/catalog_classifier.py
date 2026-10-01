#!/usr/bin/env python3
import re

GAME_SCORE_THRESHOLD = 3
UNKNOWN_SIZE_VALUES = {"", "N/A", "NA", "UNKNOWN", "-", "NONE"}

# These are editorial/site posts, but only rejected automatically when the
# record does not otherwise look like a real game. This avoids false positives
# for legitimate titles containing generic words such as "Update" or "Fix".
EDITORIAL_PATTERNS = (
    (re.compile(r"\bupdates digest\b", re.IGNORECASE), "updates-digest"),
    (re.compile(r"\bupcoming repacks\b", re.IGNORECASE), "upcoming-repacks"),
    (re.compile(r"\bdonations?\b", re.IGNORECASE), "donation-post"),
    (re.compile(r"\bstatus update\b", re.IGNORECASE), "status-update"),
    (re.compile(r"^about\s+.+\bcracks?\b", re.IGNORECASE), "crack-editorial"),
    (re.compile(r"\bproper cracks?\s+added\b", re.IGNORECASE), "crack-update"),
    (re.compile(r"\bcracks?\s+added\b", re.IGNORECASE), "crack-update"),
    (re.compile(r"\brepack\s+updated\b", re.IGNORECASE), "repack-update-post"),
    (re.compile(r"\bupdates?\s+posted\b", re.IGNORECASE), "update-post"),
    (re.compile(r"\bupdated\s+repack\s+test\b", re.IGNORECASE), "repack-test-post"),
    (
        re.compile(
            r"(?:\bissue\b.*\bdirect download links?\b|\bdirect download links?\b.*\b(?:issue|fixed)\b)",
            re.IGNORECASE,
        ),
        "site-link-status",
    ),
    (re.compile(r"^yet another fix for\b", re.IGNORECASE), "fix-post"),
    (re.compile(r"^installer fixes?$", re.IGNORECASE), "installer-fix-post"),
    (re.compile(r"^some people just can[’']t be fixed$", re.IGNORECASE), "editorial-post"),
    (re.compile(r"\bsite (?:maintenance|news|update)\b", re.IGNORECASE), "site-editorial"),
    (re.compile(r"\btest post\b", re.IGNORECASE), "test-post"),
)

# These are standalone assets/tools rather than the actual game. They are
# intentionally narrow: "+ HD Texture Pack" on a real game still passes.
STANDALONE_CONTENT_PATTERNS = (
    (
        re.compile(
            r"(?::|[–—-])\s*(?:high[- ]resolution|hd|4k)\s+texture\s+pack\b",
            re.IGNORECASE,
        ),
        "standalone-texture-pack",
    ),
    (
        re.compile(
            r"(?::|[–—-])\s*(?:original\s+)?soundtrack(?:\s+pack|\s+bundle)?\s*(?:[,–—-]|$)",
            re.IGNORECASE,
        ),
        "standalone-soundtrack",
    ),
    (
        re.compile(r"(?::|[–—-])\s*(?:digital\s+)?artbook\s*(?:[,–—-]|$)", re.IGNORECASE),
        "standalone-artbook",
    ),
    (
        re.compile(r"(?::|[–—-])\s*dedicated\s+server\b", re.IGNORECASE),
        "standalone-dedicated-server",
    ),
)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _details(record):
    value = record.get("details")
    return value if isinstance(value, dict) else {}


def score_game_signals(record):
    score = 0
    signals = []

    genres = record.get("genres")
    if isinstance(genres, list) and any(_text(item) for item in genres):
        score += 3
        signals.append("genres")

    size = _text(record.get("repack_size")).upper()
    if size not in UNKNOWN_SIZE_VALUES:
        score += 3
        signals.append("repack-size")

    if _text(record.get("image_url")):
        score += 1
        signals.append("image")

    details = _details(record)
    if _text(details.get("description")):
        score += 2
        signals.append("description")

    media = record.get("media")
    if isinstance(media, list) and media:
        score += 1
        signals.append("media")

    return score, signals


def explicit_non_game_reason(title):
    normalized = re.sub(r"\s+", " ", _text(title))
    if not normalized:
        return None

    for pattern, reason in STANDALONE_CONTENT_PATTERNS:
        if pattern.search(normalized):
            return reason

    return None


def editorial_reason(title):
    normalized = re.sub(r"\s+", " ", _text(title))
    if not normalized:
        return None

    for pattern, reason in EDITORIAL_PATTERNS:
        if pattern.search(normalized):
            return reason

    return None


def classify_record(record):
    title = _text(record.get("title"))
    score, signals = score_game_signals(record)

    if not title:
        return {
            "kind": "review",
            "reason": "missing-title",
            "score": score,
            "signals": signals,
        }

    hard_reason = explicit_non_game_reason(title)
    if hard_reason:
        return {
            "kind": "non_game",
            "reason": hard_reason,
            "score": score,
            "signals": signals,
        }

    soft_reason = editorial_reason(title)
    if soft_reason and score < GAME_SCORE_THRESHOLD:
        return {
            "kind": "non_game",
            "reason": soft_reason,
            "score": score,
            "signals": signals,
        }

    if score >= GAME_SCORE_THRESHOLD:
        return {
            "kind": "game",
            "reason": "game-signals",
            "score": score,
            "signals": signals,
        }

    return {
        "kind": "review",
        "reason": soft_reason or "insufficient-game-signals",
        "score": score,
        "signals": signals,
    }


def quarantine_entry(record, decision, action):
    return {
        "id": _text(record.get("id")),
        "title": _text(record.get("title")),
        "source_url": _text(record.get("source_url")),
        "classification": decision["kind"],
        "reason": decision["reason"],
        "score": decision["score"],
        "signals": list(decision["signals"]),
        "action": action,
    }
