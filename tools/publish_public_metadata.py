#!/usr/bin/env python3
"""Publish the sanitized metadata snapshot to one GitHub repository file.

Authentication is read from FITBOY_GITHUB_TOKEN. The token is never printed.
This script intentionally publishes exactly one generated JSON file and nothing
from the SQLite database itself.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_REPOSITORY = "Rzbck/FitBoyRepack"
DEFAULT_BRANCH = "main"
DEFAULT_PATH = "site/data/metadata-enrichment.json"
DEFAULT_INPUT = Path("/var/lib/fitboy/ai/metadata-enrichment.json")
API_VERSION = "2022-11-28"
USER_AGENT = "FitBoyRepack-MetadataPublisher/1.0"


def _request_json(
    url: str,
    *,
    token: str,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    parsed = json.loads(raw.decode("utf-8")) if raw else {}
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected GitHub API response")
    return parsed


def _contents_url(repository: str, path: str) -> str:
    safe_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return f"https://api.github.com/repos/{repository}/contents/{safe_path}"


def _content_read_url(repository: str, path: str, branch: str) -> str:
    return f"{_contents_url(repository, path)}?ref={quote(branch, safe='')}"


def _remote_content(
    repository: str,
    path: str,
    branch: str,
    token: str,
) -> tuple[str | None, bytes | None]:
    url = _content_read_url(repository, path, branch)
    try:
        payload = _request_json(url, token=token)
    except HTTPError as exc:
        if exc.code == 404:
            return None, None
        raise

    sha = str(payload.get("sha") or "").strip() or None
    encoded = payload.get("content")
    if isinstance(encoded, str):
        try:
            content = base64.b64decode(encoded.replace("\n", ""), validate=False)
        except ValueError:
            content = None
    else:
        content = None
    return sha, content


def publish_snapshot(
    input_path: Path,
    *,
    repository: str,
    path: str,
    branch: str,
    token: str,
    retries: int = 3,
) -> dict[str, object]:
    content = input_path.read_bytes()
    # Fail closed before touching GitHub.
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), dict):
        raise RuntimeError("invalid public metadata snapshot")
    if int(payload.get("count", -1)) != len(payload["games"]):
        raise RuntimeError("public metadata snapshot count mismatch")

    digest = hashlib.sha256(content).hexdigest()
    api_url = _contents_url(repository, path)

    for attempt in range(1, retries + 1):
        sha, remote = _remote_content(repository, path, branch, token)
        if remote == content:
            return {
                "changed": False,
                "count": payload["count"],
                "sha256": digest,
            }

        body: dict[str, object] = {
            "message": f"data: publish verified metadata snapshot ({payload['count']} games)",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        try:
            result = _request_json(api_url, token=token, method="PUT", payload=body)
            commit = result.get("commit") if isinstance(result.get("commit"), dict) else {}
            return {
                "changed": True,
                "count": payload["count"],
                "sha256": digest,
                "commit": str(commit.get("sha") or "")[:12],
            }
        except HTTPError as exc:
            if exc.code not in {409, 422} or attempt >= retries:
                raise
            time.sleep(float(attempt))

    raise RuntimeError("metadata publication retry loop exhausted")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish one sanitized metadata snapshot to GitHub.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--token-env", default="FITBOY_GITHUB_TOKEN")
    args = parser.parse_args()

    token = str(os.environ.get(args.token_env) or "").strip()
    if not token:
        raise RuntimeError(f"missing GitHub token in environment variable {args.token_env}")

    stats = publish_snapshot(
        args.input,
        repository=args.repository,
        path=args.path,
        branch=args.branch,
        token=token,
    )
    if stats["changed"]:
        print(
            "public metadata publish: "
            f"changed=yes count={stats['count']} commit={stats.get('commit') or '-'} "
            f"sha256={stats['sha256'][:16]}"
        )
    else:
        print(
            "public metadata publish: "
            f"changed=no count={stats['count']} sha256={stats['sha256'][:16]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
