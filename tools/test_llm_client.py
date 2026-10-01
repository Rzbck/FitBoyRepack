#!/usr/bin/env python3
import json

import httpx

from llm_client import LLMConfig, LocalLLMClient


def main():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "```json\n{\"ok\":true,\"value\":42}\n```"}}]},
        )

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    config = LLMConfig(base_url="http://127.0.0.1:8080/v1", model="test-model")
    llm = LocalLLMClient(config, client=http)
    result = llm.chat_json("return json", system="test")

    assert result == {"ok": True, "value": 42}
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["payload"]["model"] == "test-model"
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert seen["payload"]["stream"] is False
    http.close()
    print("generic local LLM client OK")


if __name__ == "__main__":
    main()
