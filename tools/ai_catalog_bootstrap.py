#!/usr/bin/env python3
"""Resumable AI metadata bootstrap for the rich game catalog.

The worker keeps all AI state in a local SQLite sidecar. It never writes
AI output into the public catalog directly. A general OpenAI-compatible LLM
service is used only for reasoning/translation; keyless Wikidata/Wikipedia
requests provide the evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from llm_client import LocalLLMClient

AI_VERSION = 1
DEFAULT_CATALOG = Path("site/data/games.json")
DEFAULT_DB = Path("data/ai/catalog_enrichment.sqlite3")
DEFAULT_THRESHOLD = 0.80
USER_AGENT = "FitBoyRepack-MetadataWorker/1.0 (personal metadata enrichment)"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
FORBIDDEN_OUTPUT_KEYS = {
    "magnet", "magnets", "torrent", "torrents", "torrent_links",
    "download", "downloads", "download_url", "download_mirrors",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_games(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise RuntimeError("catalog must be an object containing games: []")
    return [g for g in payload["games"] if isinstance(g, dict) and g.get("id") and g.get("title")]


def game_fingerprint(game: dict[str, Any]) -> str:
    details = game.get("details") if isinstance(game.get("details"), dict) else {}
    material = {
        "title": game.get("title"),
        "source_url": game.get("source_url"),
        "post_date": game.get("post_date"),
        "genres": game.get("genres"),
        "description": details.get("description"),
        "ai_version": AI_VERSION,
    }
    return hashlib.sha256(compact_json(material).encode("utf-8")).hexdigest()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            game_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','processing','done','review','failed','removed')),
            active INTEGER NOT NULL DEFAULT 1,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            queued_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS jobs_status_active_idx ON jobs(status, active, updated_at);
        CREATE TABLE IF NOT EXISTS results (
            game_id TEXT PRIMARY KEY,
            canonical_title TEXT,
            release_date TEXT,
            genres_json TEXT NOT NULL DEFAULT '[]',
            developer TEXT,
            publisher TEXT,
            platforms_json TEXT NOT NULL DEFAULT '[]',
            description_fr TEXT,
            confidence REAL NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT,
            ai_version INTEGER NOT NULL,
            checked_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            FOREIGN KEY(game_id) REFERENCES jobs(game_id) ON DELETE CASCADE
        );
        """
    )
    return conn


def initialize_queue(conn: sqlite3.Connection, games: list[dict[str, Any]]) -> dict[str, int]:
    """Sync the queue with the catalog and recover interrupted jobs safely."""
    now = utcnow()
    current_ids: set[str] = set()
    created = changed = unchanged = recovered = 0
    conn.execute("UPDATE jobs SET active=0")
    for game in games:
        game_id = str(game["id"])
        current_ids.add(game_id)
        title = str(game["title"]).strip()
        fingerprint = game_fingerprint(game)
        existing = conn.execute("SELECT fingerprint,status FROM jobs WHERE game_id=?", (game_id,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO jobs(game_id,title,fingerprint,status,active,queued_at,updated_at) VALUES(?,?,?,'pending',1,?,?)",
                (game_id, title, fingerprint, now, now),
            )
            created += 1
        elif existing["fingerprint"] != fingerprint:
            conn.execute(
                "UPDATE jobs SET title=?,fingerprint=?,status='pending',active=1,attempts=0,last_error=NULL,queued_at=?,started_at=NULL,finished_at=NULL,updated_at=? WHERE game_id=?",
                (title, fingerprint, now, now, game_id),
            )
            conn.execute("DELETE FROM results WHERE game_id=?", (game_id,))
            changed += 1
        elif existing["status"] in {"processing", "removed"}:
            conn.execute(
                "UPDATE jobs SET title=?,status='pending',active=1,last_error=NULL,queued_at=?,started_at=NULL,finished_at=NULL,updated_at=? WHERE game_id=?",
                (title, now, now, game_id),
            )
            conn.execute("DELETE FROM results WHERE game_id=?", (game_id,))
            recovered += 1
        else:
            conn.execute("UPDATE jobs SET title=?,active=1,updated_at=? WHERE game_id=?", (title, now, game_id))
            unchanged += 1
    conn.execute("UPDATE jobs SET status='removed',updated_at=? WHERE active=0 AND status!='removed'", (now,))
    conn.commit()
    removed = conn.execute("SELECT COUNT(*) FROM jobs WHERE active=0").fetchone()[0]
    return {
        "created": created, "changed": changed, "recovered": recovered,
        "unchanged": unchanged, "removed": removed, "total": len(current_ids),
    }


def queue_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {row["status"]: row["n"] for row in conn.execute("SELECT status,COUNT(*) n FROM jobs WHERE active=1 GROUP BY status")}
    counts["total"] = sum(counts.values())
    return counts


def clean_search_title(title: str) -> str:
    value = html.unescape(title).strip()
    value = re.sub(r"\s+\+\s+.*$", "", value)
    value = re.sub(r"\s+[–—-]\s+(?:v(?:ersion)?\s*)?\d[\w.\-]*(?:\s.*)?$", "", value, flags=re.I)
    value = re.sub(r"\s+v\d+(?:\.\d+)+(?:\s.*)?$", "", value, flags=re.I)
    value = re.sub(r"\s+build\s+\d+(?:\s.*)?$", "", value, flags=re.I)
    value = re.sub(r"\s{2,}", " ", value).strip(" -–—")
    return value or title.strip()


def _claim_entity_ids(claims: dict[str, Any], prop: str) -> list[str]:
    ids: list[str] = []
    for claim in claims.get(prop, []) if isinstance(claims.get(prop), list) else []:
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            ids.append(value["id"])
    return ids


def _claim_times(claims: dict[str, Any], prop: str) -> list[str]:
    values: list[str] = []
    for claim in claims.get(prop, []) if isinstance(claims.get(prop), list) else []:
        try:
            raw = str(claim["mainsnak"]["datavalue"]["value"]["time"])
        except (KeyError, TypeError):
            continue
        match = re.match(r"^[+-](\d{4})-(\d{2})-(\d{2})T", raw)
        if match:
            values.append("-".join(match.groups()))
    return sorted(set(values))


class EvidenceRetriever:
    """Fetch compact, keyless evidence from Wikidata and Wikipedia."""

    def __init__(self, client: httpx.Client | None = None):
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "EvidenceRetriever":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("unexpected metadata API response")
        return data

    def _search_wikidata(self, query: str, limit: int = 5) -> list[str]:
        data = self._get_json(WIKIDATA_API, {
            "action": "wbsearchentities", "search": query, "language": "en", "uselang": "en",
            "type": "item", "limit": limit, "format": "json",
        })
        return [item["id"] for item in data.get("search", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]

    def _entities(self, ids: list[str], props: str = "labels|descriptions|claims|sitelinks") -> dict[str, Any]:
        if not ids:
            return {}
        data = self._get_json(WIKIDATA_API, {
            "action": "wbgetentities", "ids": "|".join(ids), "props": props,
            "languages": "en|fr", "sitefilter": "enwiki", "format": "json",
        })
        return data.get("entities", {}) if isinstance(data.get("entities"), dict) else {}

    @staticmethod
    def _label(entity: dict[str, Any]) -> str | None:
        labels = entity.get("labels") if isinstance(entity.get("labels"), dict) else {}
        for language in ("en", "fr"):
            value = labels.get(language)
            if isinstance(value, dict) and value.get("value"):
                return str(value["value"])
        return None

    def _wiki_extract(self, title: str) -> tuple[str, str] | None:
        data = self._get_json(WIKIPEDIA_API, {
            "action": "query", "prop": "extracts|info", "inprop": "url", "explaintext": 1,
            "exintro": 1, "redirects": 1, "titles": title, "format": "json",
        })
        pages = ((data.get("query") or {}).get("pages") or {}) if isinstance(data.get("query"), dict) else {}
        for page in pages.values() if isinstance(pages, dict) else []:
            if not isinstance(page, dict) or page.get("missing") is not None:
                continue
            url = str(page.get("fullurl") or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}")
            extract = re.sub(r"\s+", " ", str(page.get("extract") or "")).strip()
            return url, extract[:6000]
        return None

    def fetch(self, game: dict[str, Any], candidate_limit: int = 4) -> list[dict[str, Any]]:
        title = str(game.get("title") or "").strip()
        clean = clean_search_title(title)
        entity_ids: list[str] = []
        for query in (clean, title):
            for entity_id in self._search_wikidata(query, limit=candidate_limit):
                if entity_id not in entity_ids:
                    entity_ids.append(entity_id)
                if len(entity_ids) >= candidate_limit:
                    break
            if len(entity_ids) >= candidate_limit:
                break
        entities = self._entities(entity_ids)
        linked_ids: set[str] = set()
        for entity in entities.values():
            if not isinstance(entity, dict):
                continue
            claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
            for prop in ("P136", "P178", "P123", "P400"):
                linked_ids.update(_claim_entity_ids(claims, prop))
        linked_entities = self._entities(sorted(linked_ids), props="labels")
        linked_labels = {qid: self._label(entity) or qid for qid, entity in linked_entities.items() if isinstance(entity, dict)}

        evidence: list[dict[str, Any]] = []
        for qid in entity_ids:
            entity = entities.get(qid)
            if not isinstance(entity, dict):
                continue
            claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
            descriptions = entity.get("descriptions") if isinstance(entity.get("descriptions"), dict) else {}
            desc = next((str(descriptions[lang]["value"]) for lang in ("en", "fr") if isinstance(descriptions.get(lang), dict) and descriptions[lang].get("value")), "")
            sitelinks = entity.get("sitelinks") if isinstance(entity.get("sitelinks"), dict) else {}
            enwiki = sitelinks.get("enwiki") if isinstance(sitelinks.get("enwiki"), dict) else {}
            wiki_title = str(enwiki.get("title") or "")
            wiki = self._wiki_extract(wiki_title) if wiki_title else None
            item = {
                "source": "wikidata",
                "url": f"https://www.wikidata.org/wiki/{qid}",
                "id": qid,
                "label": self._label(entity),
                "description": desc,
                "release_dates": _claim_times(claims, "P577"),
            }
            for prop, field in (("P136", "genres"), ("P178", "developers"), ("P123", "publishers"), ("P400", "platforms")):
                item[field] = [linked_labels.get(value, value) for value in _claim_entity_ids(claims, prop)]
            if wiki:
                item["wikipedia_url"], item["wikipedia_extract"] = wiki
            evidence.append(item)
        return evidence


def build_prompt(game: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[str, str]:
    details = game.get("details") if isinstance(game.get("details"), dict) else {}
    source_description = re.sub(r"\s+", " ", str(details.get("description") or "")).strip()[:7000]
    system = (
        "You clean video-game metadata using ONLY the supplied evidence. Never guess. "
        "The source post date is NOT the game's release date. Return one JSON object only. "
        "If a field is unsupported, use null or []. Translate the supplied source description faithfully into French; "
        "do not add facts. confidence is 0..1 for the identity match and metadata. evidence_urls must only contain URLs supplied in evidence. "
        "Do not output download, torrent, magnet, crack or installation links/instructions."
    )
    schema = {
        "canonical_title": "string|null",
        "release_date": "YYYY-MM-DD|null (earliest supported game release)",
        "genres": ["string"],
        "developer": "string|null",
        "publisher": "string|null",
        "platforms": ["string"],
        "description_fr": "string|null",
        "confidence": "number 0..1",
        "evidence_urls": ["https://..."],
        "notes": "short string|null",
    }
    user = compact_json({
        "task": "match this catalog entry to the correct video game and return clean metadata",
        "source_entry": {
            "id": str(game.get("id")),
            "title": game.get("title"),
            "catalog_post_date": game.get("post_date"),
            "source_genres": game.get("genres") or [],
            "source_description": source_description or None,
        },
        "evidence": evidence,
        "required_schema": schema,
    })
    return system, user


def _strings(value: Any, maximum: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text not in out:
            out.append(text[:160])
        if len(out) >= maximum:
            break
    return out


def validate_ai_result(raw: dict[str, Any], allowed_urls: set[str]) -> dict[str, Any]:
    lowered_keys = {str(key).lower() for key in raw}
    if lowered_keys & FORBIDDEN_OUTPUT_KEYS:
        raise ValueError("LLM returned a forbidden direct-download field")
    canonical = str(raw.get("canonical_title") or "").strip()[:300] or None
    release = str(raw.get("release_date") or "").strip() or None
    if release and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", release):
        release = None
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        raise ValueError("LLM confidence is missing or invalid")
    if not 0 <= confidence <= 1:
        raise ValueError("LLM confidence must be between 0 and 1")
    urls = [url for url in _strings(raw.get("evidence_urls"), 10) if url in allowed_urls]
    description = str(raw.get("description_fr") or "").strip()[:12000] or None
    notes = str(raw.get("notes") or "").strip()[:1200] or None
    return {
        "canonical_title": canonical,
        "release_date": release,
        "genres": _strings(raw.get("genres"), 12),
        "developer": str(raw.get("developer") or "").strip()[:300] or None,
        "publisher": str(raw.get("publisher") or "").strip()[:300] or None,
        "platforms": _strings(raw.get("platforms"), 24),
        "description_fr": description,
        "confidence": confidence,
        "evidence_urls": urls,
        "notes": notes,
    }


def evidence_urls(evidence: list[dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for item in evidence:
        for key in ("url", "wikipedia_url"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith("https://"):
                urls.add(value)
    return urls


def find_game(games_by_id: dict[str, dict[str, Any]], game_id: str) -> dict[str, Any]:
    game = games_by_id.get(game_id)
    if not game:
        raise RuntimeError(f"game {game_id} disappeared from catalog")
    return game


def run_batch(
    conn: sqlite3.Connection,
    games_by_id: dict[str, dict[str, Any]],
    llm: LocalLLMClient,
    retriever: EvidenceRetriever,
    *,
    limit: int = 25,
    threshold: float = DEFAULT_THRESHOLD,
    candidate_limit: int = 4,
    sleep_seconds: float = 0.0,
) -> dict[str, int]:
    processed = done = review = failed = 0
    while limit <= 0 or processed < limit:
        row = conn.execute(
            "SELECT game_id,title FROM jobs WHERE active=1 AND status='pending' ORDER BY queued_at,game_id LIMIT 1"
        ).fetchone()
        if row is None:
            break
        game_id = row["game_id"]
        started = utcnow()
        claimed = conn.execute(
            "UPDATE jobs SET status='processing',attempts=attempts+1,started_at=?,last_error=NULL,updated_at=? WHERE game_id=? AND status='pending'",
            (started, started, game_id),
        )
        conn.commit()
        if claimed.rowcount != 1:
            continue
        try:
            game = find_game(games_by_id, game_id)
            evidence = retriever.fetch(game, candidate_limit=candidate_limit)
            if not evidence:
                raise RuntimeError("no metadata evidence found")
            system, prompt = build_prompt(game, evidence)
            raw = llm.chat_json(prompt, system=system, temperature=0.05, max_tokens=1600)
            cleaned = validate_ai_result(raw, evidence_urls(evidence))
            core_complete = bool(cleaned["canonical_title"] and cleaned["release_date"] and cleaned["genres"] and cleaned["evidence_urls"])
            status = "done" if core_complete and cleaned["confidence"] >= threshold else "review"
            checked = utcnow()
            conn.execute(
                """
                INSERT INTO results(game_id,canonical_title,release_date,genres_json,developer,publisher,platforms_json,description_fr,confidence,evidence_json,notes,ai_version,checked_at,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(game_id) DO UPDATE SET
                  canonical_title=excluded.canonical_title,release_date=excluded.release_date,genres_json=excluded.genres_json,
                  developer=excluded.developer,publisher=excluded.publisher,platforms_json=excluded.platforms_json,
                  description_fr=excluded.description_fr,confidence=excluded.confidence,evidence_json=excluded.evidence_json,
                  notes=excluded.notes,ai_version=excluded.ai_version,checked_at=excluded.checked_at,raw_json=excluded.raw_json
                """,
                (
                    game_id, cleaned["canonical_title"], cleaned["release_date"], compact_json(cleaned["genres"]),
                    cleaned["developer"], cleaned["publisher"], compact_json(cleaned["platforms"]), cleaned["description_fr"],
                    cleaned["confidence"], compact_json(cleaned["evidence_urls"]), cleaned["notes"], AI_VERSION, checked, compact_json(raw),
                ),
            )
            conn.execute(
                "UPDATE jobs SET status=?,finished_at=?,updated_at=? WHERE game_id=?",
                (status, checked, checked, game_id),
            )
            done += int(status == "done")
            review += int(status == "review")
        except Exception as exc:
            when = utcnow()
            conn.execute(
                "UPDATE jobs SET status='failed',last_error=?,finished_at=?,updated_at=? WHERE game_id=?",
                (str(exc)[:2000], when, when, game_id),
            )
            failed += 1
        conn.commit()
        processed += 1
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return {"processed": processed, "done": done, "review": review, "failed": failed}


def reset_status(conn: sqlite3.Connection, status: str) -> int:
    now = utcnow()
    cursor = conn.execute(
        "UPDATE jobs SET status='pending',last_error=NULL,started_at=NULL,finished_at=NULL,queued_at=?,updated_at=? WHERE active=1 AND status=?",
        (now, now, status),
    )
    conn.commit()
    return cursor.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap clean game metadata through a reusable local LLM.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--init", action="store_true", help="queue new/changed games and recover interrupted jobs")
    parser.add_argument("--run", action="store_true", help="process pending jobs")
    parser.add_argument("--status", action="store_true", help="print queue counts")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-review", action="store_true")
    parser.add_argument("--limit", type=int, default=25, help="jobs this run; 0 means run until queue is empty")
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--candidate-limit", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.0, help="optional delay between LLM jobs")
    args = parser.parse_args()
    if not any((args.init, args.run, args.status, args.retry_failed, args.retry_review)):
        parser.error("choose at least one action: --init, --run, --status, --retry-failed or --retry-review")
    if not 0 <= args.confidence_threshold <= 1:
        parser.error("--confidence-threshold must be between 0 and 1")

    games = load_games(args.catalog)
    games_by_id = {str(game["id"]): game for game in games}
    conn = connect_db(args.db)
    try:
        if args.init:
            print("queue init:", compact_json(initialize_queue(conn, games)))
        if args.retry_failed:
            print("requeued failed:", reset_status(conn, "failed"))
        if args.retry_review:
            print("requeued review:", reset_status(conn, "review"))
        if args.run:
            with LocalLLMClient() as llm, EvidenceRetriever() as retriever:
                stats = run_batch(
                    conn, games_by_id, llm, retriever, limit=args.limit,
                    threshold=args.confidence_threshold, candidate_limit=max(1, min(args.candidate_limit, 8)),
                    sleep_seconds=max(0.0, args.sleep),
                )
            print("run:", compact_json(stats))
        if args.status or args.run or args.init:
            print("queue:", compact_json(queue_counts(conn)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
