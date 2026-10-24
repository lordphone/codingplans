"""Adversary proxy: an OpenAI-compatible middlebox that cuts corners on purpose.

vLLM can be launched quantized, with a quantized KV cache, without prefix
caching or with a smaller model under the big one's name. Some corner-cuts a
provider could make live outside the engine, in the API gateway. This proxy
simulates those, in front of any upstream server:

  truncate_tokens   middle-out truncation of the longest message to ~N tokens
  inject_system     prepend a hidden system prompt
  phantom_cache     report most prompt tokens as cached on repeated prefixes
                    (pair with an upstream started without prefix caching)
  clamp_max_tokens  silently lower max_tokens
  delay_s           sleep before forwarding each stream chunk (throttling)

Run: `planaudit lab proxy --upstream http://127.0.0.1:8100 --port 8200 --truncate-tokens 8000`
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

CHARS_PER_TOKEN = 4.0  # rough, deliberately: a real gateway would be just as crude


@dataclass
class Cuts:
    truncate_tokens: int | None = None
    inject_system: str | None = None
    phantom_cache: bool = False
    clamp_max_tokens: int | None = None
    delay_s: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Cuts:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def truncate_middle(messages: list[dict[str, Any]], max_tokens: int) -> list[dict[str, Any]]:
    """Cut the middle out of the longest message until the request fits."""
    budget = int(max_tokens * CHARS_PER_TOKEN)
    total = sum(len(str(m.get("content", ""))) for m in messages)
    if total <= budget:
        return messages
    i = max(range(len(messages)), key=lambda k: len(str(messages[k].get("content", ""))))
    content = str(messages[i]["content"])
    keep = max(0, len(content) - (total - budget))
    head = keep // 4  # keep the instructions at the start and the question at the end
    tail = keep - head
    new = content[:head] + "\n…\n" + content[len(content) - tail :]
    return [*messages[:i], {**messages[i], "content": new}, *messages[i + 1 :]]


def _prefix_key(messages: list[dict[str, Any]]) -> str:
    text = json.dumps(messages)[:4000]
    return hashlib.sha1(text.encode()).hexdigest()


def make_app(upstream: str, cuts: Cuts) -> Starlette:
    http = httpx.AsyncClient(base_url=upstream.rstrip("/"), timeout=600)
    seen: set[str] = set()

    def rewrite(body: dict[str, Any]) -> dict[str, Any]:
        msgs = list(body.get("messages", []))
        if cuts.inject_system:
            msgs = [{"role": "system", "content": cuts.inject_system}, *msgs]
        if cuts.truncate_tokens:
            msgs = truncate_middle(msgs, cuts.truncate_tokens)
        body = {**body, "messages": msgs}
        if cuts.clamp_max_tokens and body.get("max_tokens", 1 << 30) > cuts.clamp_max_tokens:
            body["max_tokens"] = cuts.clamp_max_tokens
        return body

    def fake_usage(usage: dict[str, Any], key: str, hit: bool) -> dict[str, Any]:
        if not (cuts.phantom_cache and usage):
            return usage
        pt = usage.get("prompt_tokens") or 0
        details = dict(usage.get("prompt_tokens_details") or {})
        details["cached_tokens"] = int(pt * 0.9) if hit else 0
        return {**usage, "prompt_tokens_details": details}

    async def chat(request: Request) -> Response:
        body = rewrite(await request.json())
        key = _prefix_key(body["messages"])
        hit = key in seen
        seen.add(key)
        if not body.get("stream"):
            r = await http.post("/v1/chat/completions", json=body)
            data = r.json()
            if "usage" in data:
                data["usage"] = fake_usage(data["usage"], key, hit)
            return JSONResponse(data, status_code=r.status_code)

        req = http.build_request("POST", "/v1/chat/completions", json=body)
        resp = await http.send(req, stream=True)
        if resp.status_code != 200:
            raw = await resp.aread()
            await resp.aclose()
            return Response(raw, status_code=resp.status_code, media_type="application/json")

        async def gen():
            try:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if cuts.delay_s:
                        await asyncio.sleep(cuts.delay_s)
                    if line.startswith("data:") and cuts.phantom_cache and '"usage"' in line:
                        payload = line[5:].strip()
                        if payload != "[DONE]":
                            chunk = json.loads(payload)
                            if chunk.get("usage"):
                                chunk["usage"] = fake_usage(chunk["usage"], key, hit)
                            line = "data: " + json.dumps(chunk)
                    yield line + "\n\n"
            finally:
                await resp.aclose()

        return StreamingResponse(gen(), media_type="text/event-stream")

    async def passthrough(request: Request) -> Response:
        r = await http.request(request.method, request.url.path)
        return Response(r.content, status_code=r.status_code, media_type="application/json")

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat, methods=["POST"]),
            Route("/v1/models", passthrough),
            Route("/health", passthrough),
        ],
        on_shutdown=[http.aclose],
    )
