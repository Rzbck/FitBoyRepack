#!/usr/bin/env python3
"""Consistent online SQLite backups. No secret files or live DB writes."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

SOURCES = {
    "catalog_enrichment.sqlite3": "ai/catalog_enrichment.sqlite3",
    "translations.sqlite3": "translation/translations.sqlite3",
}
STAMP = re.compile(r"^\d{8}T\d{6}Z$")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def copy_db(source, target):
    if not source.is_file():
        raise FileNotFoundError(source)
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=30) as src:
        src.execute("PRAGMA query_only=ON")
        with sqlite3.connect(target) as dst:
            src.backup(dst, pages=256, sleep=0.05)
            if dst.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError(f"Invalid backup: {source.name}")
            tables = dst.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            counts = {}
            for (name,) in tables:
                identifier = '"' + name.replace('"', '""') + '"'
                counts[name] = dst.execute("SELECT count(*) FROM " + identifier).fetchone()[0]
    target.chmod(0o600)
    return {"size": target.stat().st_size, "sha256": digest(target), "tables": counts}


def backup(root, destination, keep=14):
    os.umask(0o077)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (destination / ".backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=destination))
        final = destination / stamp
        try:
            manifest = {"created_at": stamp, "format": 1, "databases": {}}
            for filename, relative in SOURCES.items():
                manifest["databases"][filename] = copy_db(root / relative, stage / filename)
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            for path in stage.iterdir():
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
            stage.rename(final)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        # Retain only snapshots made by this program; never touch other backup files.
        snapshots = sorted(
            p for p in destination.iterdir()
            if p.is_dir() and not p.is_symlink() and STAMP.fullmatch(p.name)
            and (p / "manifest.json").is_file()
        )
        for old in snapshots[:-keep]:
            shutil.rmtree(old)
        print(json.dumps({"backup": str(final), **manifest}, sort_keys=True))
        return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/var/lib/fitboy"))
    parser.add_argument("--destination", type=Path, default=Path("/var/lib/fitboy/backups"))
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    if args.keep < 2:
        parser.error("keep must be >= 2")
    backup(args.root, args.destination, args.keep)
