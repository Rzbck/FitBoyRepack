#!/usr/bin/env python3
"""Small OpenAI-compatible client for a reusable local LLM service.

The service is intentionally project-agnostic. Any local script can import
``LocalLLMClient`` or call this file as a tiny CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "local-model"
    api_key: str = ""
    timeout: float = 120.0
    max_tokens: int = 1200
    temperature: float = 0.1

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.getenv("LLM_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("LLM_MODEL", cls.model),
            api_key=os.getenv("LLM_API_KEY", ""),
            timeout=float(os.getenv("LLM_TIMEOUT", str(cls.timeout))),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", str(cls.max_tokens))),
            temperature=float(os.getenv("LLM_TEMPERATURE", str(cls.temperature))),
        )


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response does not contain a JSON object")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON response must be an object")
    return parsed


class LocalLLMClient:
    def __init__(self, config: LLMConfig | None = None, client: httpx.Client | None = None):
        self.config = config or LLMConfig.from_env()
        self._owns_client = client is None
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        self.client = client or httpx.Client(timeout=self.config.timeout, headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "LocalLLMClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def chat(
        self,
        user: str,
        *,
        system: str = "You are a concise helpful assistant.",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        response = self.client.post(f"{self.config.base_url}/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected OpenAI-compatible LLM response") from exc

    def chat_json(
        self,
        user: str,
        *,
        system: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        response = self.client.post(f"{self.config.base_url}/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        try:
            text = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected OpenAI-compatible LLM response") from exc
        return _extract_json(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Talk to the reusable local OpenAI-compatible LLM service.")
    parser.add_argument("prompt")
    parser.add_argument("--system", default="You are a concise helpful assistant.")
    parser.add_argument("--json", action="store_true", dest="json_mode")
    args = parser.parse_args()
    with LocalLLMClient() as llm:
        if args.json_mode:
            print(json.dumps(llm.chat_json(args.prompt, system=args.system), ensure_ascii=False, indent=2))
        else:
            print(llm.chat(args.prompt, system=args.system))


if __name__ == "__main__":
    main()
