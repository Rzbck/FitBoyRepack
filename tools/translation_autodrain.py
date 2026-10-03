#!/usr/bin/env python3
"""Resumable background EN->FR translation worker for public game prose.

The worker translates only catalog descriptions and game feature text. It never
touches repack instructions, source URLs, download data or the English source.
Each source field is fingerprinted and cached in SQLite; unchanged fields are
never translated twice. The translation model is loaded only when eligible work
is pending, then the process exits so RAM is released.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKER_VERSION = 1
MODEL_ID = "Helsinki-NLP/opus-mt-tc-big-en-fr"
DEFAULT_CATALOG = Path("/opt/FitBoyRepack/site/data/games.json")
DEFAULT_METADATA = Path("/opt/FitBoyRepack/site/data/metadata-enrichment.json")
DEFAULT_DB = Path("/var/lib/fitboy/translation/translations.sqlite3")
DEFAULT_MODEL = Path("/var/lib/fitboy/translation/model-int8")
DEFAULT_TOKENIZER = Path("/var/lib/fitboy/translation/tokenizer")
DEFAULT_LIMIT = 24
DEFAULT_MAX_ERROR_ATTEMPTS = 3
DEFER_SERVICES = ("metadata-autodrain.service", "review-llm.service")

EN_COMMON = {
    "the", "and", "with", "from", "into", "this", "that", "your", "you",
    "are", "for", "where", "have", "has", "will", "can", "their", "while",
    "through", "against", "of", "to", "in", "on",
}
FR_COMMON = {
    "le", "la", "les", "un", "une", "des", "avec", "dans", "sur", "pour",
    "vous", "votre", "est", "sont", "qui", "que", "aux", "par", "et", "du",
}
TITLE_STOPWORDS = {
    "the", "of", "and", "a", "an", "to", "in", "on", "for", "with", "from",
    "edition", "complete", "deluxe", "definitive", "game", "bundle", "pack",
    "bonus", "soundtrack", "dlc", "dlcs",
}
QID_RE = re.compile(r"^Q\d+$", re.I)
FIELD_RE = re.compile(r"^game_feature:(\d{4})$")
LEFTOVER_PLACEHOLDER_RE = re.compile(r"ZXQ[A-Z0-9]*QXZ")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: object) -> str:
    decomposed = unicodedata.normalize("NFD", clean(value))
    asciiish = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", asciiish.lower()).strip()


def looks_english(text: str) -> bool:
    words = re.findall(r"[A-Za-z']+", text.lower())
    if len(words) < 6:
        return True
    en = sum(word in EN_COMMON for word in words)
    fr = sum(word in FR_COMMON for word in words)
    return en >= 3 and en > fr


def english_leak_score(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text.lower())
    if not words:
        return 0.0
    return sum(word in EN_COMMON for word in words) / len(words)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def load_metadata(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    games = payload.get("games")
    if not isinstance(games, dict):
        return {}
    return {
        str(game_id): value
        for game_id, value in games.items()
        if str(game_id).strip() and isinstance(value, dict)
    }


def as_terms(value: object) -> list[str]:
    if isinstance(value, str):
        item = clean(value)
        return [item] if item else []
    if isinstance(value, list):
        return [clean(item) for item in value if clean(item)]
    return []


def title_variants(title: str) -> list[str]:
    """Return conservative variants derived only from one known title."""
    title = clean(title)
    if not title:
        return []

    base = re.split(
        r"\s+[–—-]\s+(?=(?:v?\d|build\b|complete\b|deluxe\b|definitive\b|\d+\s+DLC))",
        title,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    values = {base or title}

    if ":" in base:
        left = clean(base.split(":", 1)[0])
        if len(left) >= 4:
            values.add(left)

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.-]*", base)
    meaningful = [word for word in words if word.lower() not in TITLE_STOPWORDS]

    for index in range(len(meaningful) - 1):
        first, second = meaningful[index], meaningful[index + 1]
        if len(first) >= 3 and len(second) >= 3:
            values.add(f"{first} {second}")

    for word in meaningful:
        if (
            len(word) >= 8
            and re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", word)
            and word.lower() not in TITLE_STOPWORDS
        ):
            values.add(word)

    return sorted(values, key=lambda value: (-len(value), value.casefold()))


def allowed_terms(game: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    canonical = clean(metadata.get("canonical_title"))
    raw = clean(game.get("title"))

    if canonical:
        values.extend(title_variants(canonical))
    elif raw:
        values.extend(title_variants(raw))

    values.extend(as_terms(metadata.get("developer")))
    values.extend(as_terms(metadata.get("publisher")))

    unique: list[str] = []
    for value in values:
        value = clean(value)
        if len(value) < 3 or QID_RE.fullmatch(value):
            continue
        if value not in unique:
            unique.append(value)

    return sorted(unique, key=lambda value: (-len(value), value.casefold()))


def source_fields(game: dict[str, Any]) -> list[tuple[str, str]]:
    details = game.get("details")
    if not isinstance(details, dict):
        return []

    fields: list[tuple[str, str]] = []
    description = clean(details.get("description"))
    if len(description) >= 40 and looks_english(description):
        fields.append(("description", description))

    features = details.get("game_features")
    if isinstance(features, list):
        for index, value in enumerate(features):
            text = clean(value)
            if len(text) >= 12 and looks_english(text):
                fields.append((f"game_feature:{index:04d}", text))
    return fields


def source_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint(text: str, terms: list[str]) -> str:
    payload = json.dumps(
        {
            "worker_version": WORKER_VERSION,
            "source": text,
            "terms": terms,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS translation_jobs (
            game_id TEXT NOT NULL,
            field_key TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            source_text TEXT NOT NULL,
            terms_json TEXT NOT NULL,
            worker_version INTEGER NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('pending','processing','done','rejected','error')),
            attempts INTEGER NOT NULL DEFAULT 0,
            translated_text TEXT,
            last_error TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(game_id, field_key)
        );
        CREATE INDEX IF NOT EXISTS idx_translation_jobs_work
          ON translation_jobs(active, status, attempts, updated_at);
        CREATE TABLE IF NOT EXISTS translation_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_fingerprint(catalog_path: Path, metadata_path: Path) -> str:
    payload = (
        f"worker={WORKER_VERSION}\n"
        f"catalog={file_sha256(catalog_path)}\n"
        f"metadata={file_sha256(metadata_path)}\n"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def meta_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM translation_meta WHERE key=?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row is not None else None


def set_meta_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO translation_meta(key,value,updated_at)
        VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET
          value=excluded.value,
          updated_at=excluded.updated_at
        """,
        (key, value, utcnow()),
    )
    conn.commit()


def recover_interrupted(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        UPDATE translation_jobs
        SET status='pending',
            last_error='interrupted activation',
            updated_at=?
        WHERE status='processing'
        """,
        (utcnow(),),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def sync_queue(
    conn: sqlite3.Connection,
    games: list[dict[str, Any]],
    metadata_games: dict[str, dict[str, Any]],
) -> dict[str, int]:
    now = utcnow()
    conn.execute("UPDATE translation_jobs SET active=0")

    seen = queued = changed = unchanged = 0
    for game in games:
        if not isinstance(game, dict):
            continue
        game_id = clean(game.get("id"))
        if not game_id:
            continue
        terms = allowed_terms(game, metadata_games.get(game_id, {}))
        terms_json = json.dumps(terms, ensure_ascii=False, separators=(",", ":"))

        for field_key, text in source_fields(game):
            seen += 1
            fp = fingerprint(text, terms)
            sha = source_sha256(text)
            row = conn.execute(
                "SELECT fingerprint,worker_version FROM translation_jobs "
                "WHERE game_id=? AND field_key=?",
                (game_id, field_key),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO translation_jobs(
                        game_id,field_key,fingerprint,source_sha256,source_text,terms_json,
                        worker_version,status,attempts,translated_text,last_error,active,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,'pending',0,NULL,NULL,1,?,?)
                    """,
                    (game_id, field_key, fp, sha, text, terms_json, WORKER_VERSION, now, now),
                )
                queued += 1
            elif row["fingerprint"] != fp or int(row["worker_version"]) != WORKER_VERSION:
                conn.execute(
                    """
                    UPDATE translation_jobs
                    SET fingerprint=?,source_sha256=?,source_text=?,terms_json=?,
                        worker_version=?,status='pending',attempts=0,
                        translated_text=NULL,last_error=NULL,active=1,updated_at=?
                    WHERE game_id=? AND field_key=?
                    """,
                    (fp, sha, text, terms_json, WORKER_VERSION, now, game_id, field_key),
                )
                changed += 1
            else:
                conn.execute(
                    """
                    UPDATE translation_jobs
                    SET source_text=?,source_sha256=?,terms_json=?,active=1,updated_at=?
                    WHERE game_id=? AND field_key=?
                    """,
                    (text, sha, terms_json, now, game_id, field_key),
                )
                unchanged += 1

    conn.commit()
    active = int(
        conn.execute("SELECT COUNT(*) FROM translation_jobs WHERE active=1").fetchone()[0]
    )
    return {
        "seen": seen,
        "queued": queued,
        "changed": changed,
        "unchanged": unchanged,
        "active": active,
    }


def queue_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {
        str(row["status"]): int(row["n"])
        for row in conn.execute(
            "SELECT status,COUNT(*) AS n FROM translation_jobs "
            "WHERE active=1 GROUP BY status"
        )
    }
    counts["active"] = sum(counts.values())
    return counts


def service_active(name: str) -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "--quiet", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def split_sentences(text: str) -> list[str]:
    text = clean(text)
    if not text:
        return []
    return [
        item.strip()
        for item in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“‘(\[])', text)
        if item.strip()
    ]


def protect_sentence(sentence: str, terms: list[str]) -> tuple[str, dict[str, str]]:
    masked = sentence
    mapping: dict[str, str] = {}
    counter = 0

    for term in terms:
        if term not in masked:
            continue
        counter += 1
        placeholder = f"ZXQ{counter:02d}QXZ"
        masked = masked.replace(term, placeholder)
        mapping[placeholder] = term
    return masked, mapping


def restore_sentence(text: str, mapping: dict[str, str]) -> tuple[str, list[str], list[str]]:
    missing: list[str] = []
    for placeholder, original in mapping.items():
        if placeholder not in text:
            missing.append(placeholder)
        else:
            text = text.replace(placeholder, original)
    leftovers = LEFTOVER_PLACEHOLDER_RE.findall(text)
    return text, missing, leftovers


class TranslationRejected(RuntimeError):
    pass


def load_runtime(model_path: Path, tokenizer_path: Path):
    import ctranslate2
    from transformers import AutoTokenizer

    translator = ctranslate2.Translator(
        str(model_path),
        device="cpu",
        compute_type="int8",
        inter_threads=1,
        intra_threads=1,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        str(tokenizer_path),
        local_files_only=True,
    )
    return translator, tokenizer


def translate_field(
    text: str,
    terms: list[str],
    *,
    translator: Any,
    tokenizer: Any,
) -> str:
    sentences = split_sentences(text)
    if not sentences:
        raise TranslationRejected("empty source after sentence split")

    prepared: list[dict[str, Any]] = []
    for sentence in sentences:
        masked, mapping = protect_sentence(sentence, terms)
        token_ids = tokenizer.encode(masked, add_special_tokens=True)
        prepared.append(
            {
                "source": sentence,
                "mapping": mapping,
                "tokens": tokenizer.convert_ids_to_tokens(token_ids),
            }
        )

    outputs = translator.translate_batch(
        [item["tokens"] for item in prepared],
        beam_size=4,
        patience=1,
        max_batch_size=8,
        max_decoding_length=256,
    )

    if len(outputs) != len(prepared):
        raise TranslationRejected("translation output count mismatch")

    translated_sentences: list[str] = []
    for item, output in zip(prepared, outputs):
        output_ids = tokenizer.convert_tokens_to_ids(output.hypotheses[0])
        translated = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        restored, missing, leftovers = restore_sentence(translated, item["mapping"])

        if missing or leftovers:
            raise TranslationRejected("placeholder validation failed")
        if not restored:
            raise TranslationRejected("empty translated sentence")

        ratio = len(restored) / max(1, len(item["source"]))
        if ratio < 0.30 or ratio > 2.20:
            raise TranslationRejected(f"implausible length ratio {ratio:.3f}")

        if len(restored) >= 80 and english_leak_score(restored) >= 0.20:
            raise TranslationRejected("excessive English residue")

        translated_sentences.append(restored)

    return " ".join(translated_sentences)


def pending_rows(
    conn: sqlite3.Connection,
    *,
    limit: int,
    max_error_attempts: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT game_id,field_key,fingerprint,source_text,terms_json,status,attempts
        FROM translation_jobs
        WHERE active=1
          AND (
            status='pending'
            OR (status='error' AND attempts < ?)
          )
        ORDER BY
          CASE WHEN field_key='description' THEN 0 ELSE 1 END,
          updated_at,game_id,field_key
        LIMIT ?
        """,
        (max_error_attempts, limit),
    ).fetchall()


def process_rows(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    model_path: Path,
    tokenizer_path: Path,
) -> dict[str, int]:
    if not rows:
        return {"attempted": 0, "done": 0, "rejected": 0, "errors": 0}

    print(f"[TRANSLATE] loading model={MODEL_ID}", flush=True)
    translator, tokenizer = load_runtime(model_path, tokenizer_path)

    done = rejected = errors = 0
    for row in rows:
        game_id = str(row["game_id"])
        field_key = str(row["field_key"])
        fingerprint_value = str(row["fingerprint"])
        attempts = int(row["attempts"]) + 1
        now = utcnow()

        conn.execute(
            """
            UPDATE translation_jobs
            SET status='processing',attempts=?,last_error=NULL,updated_at=?
            WHERE game_id=? AND field_key=? AND fingerprint=?
            """,
            (attempts, now, game_id, field_key, fingerprint_value),
        )
        conn.commit()

        try:
            terms_raw = json.loads(str(row["terms_json"] or "[]"))
            terms = [clean(value) for value in terms_raw if clean(value)] if isinstance(terms_raw, list) else []
            translated = translate_field(
                str(row["source_text"]),
                terms,
                translator=translator,
                tokenizer=tokenizer,
            )
        except TranslationRejected as exc:
            conn.execute(
                """
                UPDATE translation_jobs
                SET status='rejected',translated_text=NULL,last_error=?,updated_at=?
                WHERE game_id=? AND field_key=? AND fingerprint=?
                """,
                (clean(exc)[:500], utcnow(), game_id, field_key, fingerprint_value),
            )
            conn.commit()
            rejected += 1
            print(
                f"[TRANSLATE] game_id={game_id} field={field_key} outcome=rejected "
                f"reason={clean(exc)[:160]!r}",
                flush=True,
            )
        except Exception as exc:
            conn.execute(
                """
                UPDATE translation_jobs
                SET status='error',translated_text=NULL,last_error=?,updated_at=?
                WHERE game_id=? AND field_key=? AND fingerprint=?
                """,
                (clean(exc)[:500], utcnow(), game_id, field_key, fingerprint_value),
            )
            conn.commit()
            errors += 1
            print(
                f"[TRANSLATE] game_id={game_id} field={field_key} outcome=error "
                f"type={type(exc).__name__} detail={clean(exc)[:160]!r}",
                flush=True,
            )
        else:
            conn.execute(
                """
                UPDATE translation_jobs
                SET status='done',translated_text=?,last_error=NULL,updated_at=?
                WHERE game_id=? AND field_key=? AND fingerprint=?
                """,
                (translated, utcnow(), game_id, field_key, fingerprint_value),
            )
            conn.commit()
            done += 1
            print(
                f"[TRANSLATE] game_id={game_id} field={field_key} outcome=done "
                f"chars={len(translated)}",
                flush=True,
            )

    return {
        "attempted": len(rows),
        "done": done,
        "rejected": rejected,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumable background French translation worker.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--tokenizer", type=Path, default=DEFAULT_TOKENIZER)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--max-error-attempts", type=int, default=DEFAULT_MAX_ERROR_ATTEMPTS)
    parser.add_argument("--ignore-busy-services", action="store_true")
    args = parser.parse_args()

    if args.limit <= 0 or args.max_error_attempts <= 0:
        parser.error("--limit and --max-error-attempts must be greater than zero")

    if not args.ignore_busy_services:
        busy = [service for service in DEFER_SERVICES if service_active(service)]
        if busy:
            print(f"[TRANSLATE] deferred busy_services={','.join(busy)}", flush=True)
            return 0

    conn = connect_db(args.db)
    try:
        recovered = recover_interrupted(conn)
        if recovered:
            print(f"[TRANSLATE] recovered_interrupted={recovered}", flush=True)

        inputs = input_fingerprint(args.catalog, args.metadata)
        previous_inputs = meta_value(conn, "inputs_fingerprint")

        if previous_inputs != inputs:
            source_payload = load_json(args.catalog)
            games = source_payload.get("games")
            if not isinstance(games, list):
                raise RuntimeError("catalog must contain games: []")
            metadata_games = load_metadata(args.metadata)
            stats = sync_queue(conn, games, metadata_games)
            set_meta_value(conn, "inputs_fingerprint", inputs)
            print("[TRANSLATE] sync=" + json.dumps(stats, separators=(",", ":")), flush=True)
        else:
            print("[TRANSLATE] sync=skipped inputs_unchanged=yes", flush=True)

        print("[TRANSLATE] queue_before=" + json.dumps(queue_counts(conn), separators=(",", ":")), flush=True)

        rows = pending_rows(
            conn,
            limit=args.limit,
            max_error_attempts=args.max_error_attempts,
        )
        if not rows:
            print("[TRANSLATE] no eligible pending fields; model remains unloaded", flush=True)
            return 0

        if not args.model.exists():
            raise RuntimeError(f"translation model missing: {args.model}")
        if not args.tokenizer.exists():
            raise RuntimeError(f"translation tokenizer missing: {args.tokenizer}")

        result = process_rows(
            conn,
            rows,
            model_path=args.model,
            tokenizer_path=args.tokenizer,
        )
        print("[TRANSLATE] run=" + json.dumps(result, separators=(",", ":")), flush=True)
        print("[TRANSLATE] queue_after=" + json.dumps(queue_counts(conn), separators=(",", ":")), flush=True)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
