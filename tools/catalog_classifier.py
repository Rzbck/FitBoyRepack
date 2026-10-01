#!/usr/bin/env python3
import re

GAME_SCORE_THRESHOLD = 3
UNKNOWN_SIZE_VALUES = {"", "N/A", "NA", "UNKNOWN", "-", "NONE"}

# Aggregate/editorial pages can embed complete metadata from games they mention.
# These known aggregate titles must therefore win over every positive game signal.
HARD_EDITORIAL_PATTERNS = (
    (re.compile(r"^updates digest\b", re.IGNORECASE), "updates-digest"),
    (re.compile(r"^upcoming repacks\b", re.IGNORECASE), "upcoming-repacks"),
)

# Editorial/site posts are rejected only when the record does not otherwise
# have enough game metadata. Generic words such as Update/Fix/DLC are never
# sufficient on their own. Keep these patterns descriptive of a post *about*
# the catalog/site rather than a game title.
EDITORIAL_PATTERNS = (
    (re.compile(r"\bupdates digest\b", re.IGNORECASE), "updates-digest"),
    (re.compile(r"\bupcoming repacks\b", re.IGNORECASE), "upcoming-repacks"),
    (re.compile(r"\bdonations?\b", re.IGNORECASE), "donation-post"),
    (re.compile(r"\bbrowser mining\b", re.IGNORECASE), "donation-post"),
    (re.compile(r"\bstatus update\b", re.IGNORECASE), "status-update"),
    (re.compile(r"\brepacks? status\b", re.IGNORECASE), "repack-status"),
    (re.compile(r"\brepack vote\b", re.IGNORECASE), "repack-vote"),
    (re.compile(r"\brip or repack\?", re.IGNORECASE), "repack-poll"),
    (re.compile(r"\brepack details\s*$", re.IGNORECASE), "repack-info-post"),
    (re.compile(r"^about\s+.+\bcracks?\b", re.IGNORECASE), "crack-editorial"),
    (re.compile(r"^about\s+.+\brelease\s*$", re.IGNORECASE), "release-editorial"),
    (re.compile(r"^about compression speed\s*$", re.IGNORECASE), "compression-editorial"),
    (re.compile(r"\bproper cracks?\s+added\b", re.IGNORECASE), "crack-update"),
    (re.compile(r"\bcracks?\s+added\b", re.IGNORECASE), "crack-update"),
    (re.compile(r"\bcrackfix\b", re.IGNORECASE), "crack-update"),
    (re.compile(r"\bcracked\b.*\bcracks?\b", re.IGNORECASE), "crack-news"),
    (re.compile(r"^cpy is on fire!?$", re.IGNORECASE), "crack-news"),
    (re.compile(r"\bdenuvo\b.*\bversus\b", re.IGNORECASE), "crack-news"),
    (re.compile(r"\brepack\s+updated\b", re.IGNORECASE), "repack-update-post"),
    (re.compile(r"\bupdates?\s+posted\b", re.IGNORECASE), "update-post"),
    (re.compile(r"\bupdated\s+repack\s+test\b", re.IGNORECASE), "repack-test-post"),
    (re.compile(r"\bpatch to v?\d", re.IGNORECASE), "patch-post"),
    (re.compile(r"\b(?:decompression|compression) test\b", re.IGNORECASE), "compression-test"),
    (re.compile(r"\bwanted for testing\b", re.IGNORECASE), "testing-request"),
    (re.compile(r"^a warning to\b", re.IGNORECASE), "site-warning"),
    (re.compile(r"\bddos\b", re.IGNORECASE), "site-incident"),
    (re.compile(r"^dns problems?\s*$", re.IGNORECASE), "site-incident"),
    (re.compile(r"^all genres/tags are now links!?$", re.IGNORECASE), "site-feature-post"),
    (re.compile(r"^all game uploads restored!?$", re.IGNORECASE), "upload-status"),
    (re.compile(r"\bday of requests\b", re.IGNORECASE), "request-event"),
    (re.compile(r"^delays in repacking\s*$", re.IGNORECASE), "repack-status"),
    (re.compile(r"\bmining faq\b", re.IGNORECASE), "site-faq"),
    (re.compile(r"\bneeds your help\b", re.IGNORECASE), "community-post"),
    (re.compile(r"\brip,?\s+anyone need it\??", re.IGNORECASE), "repack-poll"),
    (re.compile(r"^amelie report\b", re.IGNORECASE), "site-report"),
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

# High-confidence standalone content. Keep this list deliberately tiny.
# Soundtrack Bundle, Artbook and Dedicated Server are NOT safe title-only
# exclusions: the source commonly uses those words in complete game repacks.
STANDALONE_CONTENT_PATTERNS = (
    (
        re.compile(
            r"(?::|[–—-])\s*(?:high[- ]resolution|hd|4k)\s+texture\s+pack\s*[–—-]\s*for\s+v?\d",
            re.IGNORECASE,
        ),
        "standalone-texture-pack",
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


def _normalized_title(title):
    return re.sub(r"\s+", " ", _text(title))


def hard_editorial_reason(title):
    normalized = _normalized_title(title)
    if not normalized:
        return None
    for pattern, reason in HARD_EDITORIAL_PATTERNS:
        if pattern.search(normalized):
            return reason
    return None


def explicit_non_game_reason(title):
    normalized = _normalized_title(title)
    if not normalized:
        return None
    for pattern, reason in STANDALONE_CONTENT_PATTERNS:
        if pattern.search(normalized):
            return reason
    return None


def editorial_reason(title):
    normalized = _normalized_title(title)
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
        return {"kind": "review", "reason": "missing-title", "score": score, "signals": signals}

    hard_reason = hard_editorial_reason(title) or explicit_non_game_reason(title)
    if hard_reason:
        return {"kind": "non_game", "reason": hard_reason, "score": score, "signals": signals}

    soft_reason = editorial_reason(title)
    if soft_reason and score < GAME_SCORE_THRESHOLD:
        return {"kind": "non_game", "reason": soft_reason, "score": score, "signals": signals}

    if score >= GAME_SCORE_THRESHOLD:
        return {"kind": "game", "reason": "game-signals", "score": score, "signals": signals}

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
