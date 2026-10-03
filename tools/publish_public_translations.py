#!/usr/bin/env python3
"""Publish one sanitized French translation snapshot to GitHub.

Authentication is read from FITBOY_GITHUB_TOKEN. The token is never printed.
Only the generated public JSON snapshot is sent to GitHub.
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
DEFAULT_PATH = "site/data/translations-fr.json"
DEFAULT_INPUT = Path("/var/lib/fitboy/translation/translations-fr.json")
API_VERSION = "2022-11-28"
USER_AGENT = "FitBoyRepack-TranslationPublisher/1.0"


def _request_bytes(url: str, *, token: str, accept: str = "application/vnd.github.raw+json") -> bytes:
    request = Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


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
    encoding = str(payload.get("encoding") or "").lower()

    content: bytes | None = None
    if isinstance(encoded, str) and encoded and encoding != "none":
        try:
            content = base64.b64decode(encoded.replace("\n", ""), validate=False)
        except ValueError:
            content = None

    if content is None and sha:
        content = _request_bytes(url, token=token)

    return sha, content


def _semantic_payload(content: bytes | None) -> dict[str, object] | None:
    if content is None:
        return None
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    comparable = dict(payload)
    comparable.pop("generated_at", None)
    return comparable


def _same_snapshot(left: bytes | None, right: bytes | None) -> bool:
    left_payload = _semantic_payload(left)
    right_payload = _semantic_payload(right)
    return left_payload is not None and right_payload is not None and left_payload == right_payload


def _validate_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("invalid public translation snapshot")
    if payload.get("translation_version") != 1 or payload.get("language") != "fr":
        raise RuntimeError("unsupported public translation snapshot")
    games = payload.get("games")
    if not isinstance(games, dict):
        raise RuntimeError("public translation snapshot must contain games: {}")
    if int(payload.get("count", -1)) != len(games):
        raise RuntimeError("public translation snapshot count mismatch")

    fields = 0
    for game in games.values():
        if not isinstance(game, dict):
            raise RuntimeError("invalid public translation game entry")
        description = game.get("description")
        if isinstance(description, dict):
            fields += 1
        features = game.get("game_features")
        if isinstance(features, dict):
            fields += len(features)

    if int(payload.get("field_count", -1)) != fields:
        raise RuntimeError("public translation field count mismatch")
    return payload


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
    payload = _validate_payload(json.loads(content.decode("utf-8")))
    digest = hashlib.sha256(content).hexdigest()
    api_url = _contents_url(repository, path)

    for attempt in range(1, retries + 1):
        sha, remote = _remote_content(repository, path, branch, token)
        if remote == content or _same_snapshot(remote, content):
            return {
                "changed": False,
                "count": payload["count"],
                "field_count": payload["field_count"],
                "sha256": digest,
            }

        body: dict[str, object] = {
            "message": (
                "data: publish French translations "
                f"({payload['count']} games, {payload['field_count']} fields)"
            ),
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
                "field_count": payload["field_count"],
                "sha256": digest,
                "commit": str(commit.get("sha") or "")[:12],
            }
        except HTTPError as exc:
            if exc.code not in {409, 422} or attempt >= retries:
                raise
            time.sleep(float(attempt))

    raise RuntimeError("translation publication retry loop exhausted")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish one sanitized French translation snapshot.")
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
    print(
        "public translation publish: "
        f"changed={'yes' if stats['changed'] else 'no'} "
        f"games={stats['count']} fields={stats['field_count']} "
        f"commit={stats.get('commit') or '-'} sha256={stats['sha256'][:16]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
