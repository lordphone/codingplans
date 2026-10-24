"""Streaming OpenAI-compatible chat client with per-request timing.

Every request is streamed so time-to-first-token is measured the same way
for every endpoint. A `Completion` never raises: transport and HTTP errors
are recorded on the result so a run keeps going and the failure rate itself
becomes data.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from . import __version__
from .catalog import Endpoint

DEFAULT_UA = f"planaudit/{__version__} (+https://github.com/lordphone/codingplans)"
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


@dataclass
class Request:
    messages: list[dict[str, Any]]
    max_tokens: int
    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = None
    top_logprobs: int = 0  # > 0 asks for logprobs with this many alternatives
    stop: list[str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def body(self, endpoint: Endpoint, *, thinking_off: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": endpoint.api_model,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.top_p is not None:
            body["top_p"] = self.top_p
        if self.seed is not None:
            body["seed"] = self.seed
        if self.top_logprobs > 0:
            body["logprobs"] = True
            body["top_logprobs"] = self.top_logprobs
        if self.stop:
            body["stop"] = self.stop
        if thinking_off and endpoint.thinking_off:
            body.update(endpoint.thinking_off)
        body.update(endpoint.extra_params)
        body.update(self.extra)
        return body


@dataclass
class Completion:
    text: str = ""
    reasoning: str = ""
    finish_reason: str | None = None
    served_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    ttft_s: float | None = None  # first token of any kind (reasoning or content)
    ttfc_s: float | None = None  # first visible content token
    latency_s: float | None = None
    chunks: int = 0
    # Per generated token: [token, logprob, [[alt_token, alt_logprob], ...]]
    logprobs: list[list[Any]] | None = None
    status: int | None = None
    error: str | None = None
    attempts: int = 1
    started_at: float = 0.0  # unix time, for time-of-day analysis
    score: dict[str, Any] | None = None  # filled by Probe.score at collection time

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def decode_tps(self) -> float | None:
        """Single-stream decode speed: tokens after the first / time after the first."""
        if not (self.ok and self.completion_tokens and self.ttft_s and self.latency_s):
            return None
        span = self.latency_s - self.ttft_s
        if self.completion_tokens < 2 or span <= 0:
            return None
        return (self.completion_tokens - 1) / span

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and (v != "" or k == "text")}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Completion:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _parse_logprobs(choice: dict[str, Any]) -> list[list[Any]]:
    lp = choice.get("logprobs") or {}
    out = []
    for t in lp.get("content") or []:
        top = [
            [a.get("token", ""), float(a.get("logprob", 0.0))] for a in t.get("top_logprobs") or []
        ]
        out.append([t.get("token", ""), float(t.get("logprob", 0.0)), top])
    return out


class ChatClient:
    """One client per endpoint. Enforces that endpoint's concurrency and pacing."""

    def __init__(
        self,
        endpoint: Endpoint,
        *,
        timeout_s: float = 300.0,
        max_retries: int = 4,
        max_concurrency: int | None = None,
        min_interval_s: float | None = None,
    ):
        self.endpoint = endpoint
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(max_concurrency or endpoint.max_concurrency)
        self._interval = endpoint.min_interval_s if min_interval_s is None else min_interval_s
        self._pace_lock = asyncio.Lock()
        self._next_start = 0.0
        headers = {"User-Agent": endpoint.user_agent or DEFAULT_UA}
        if endpoint.api_key:
            headers["Authorization"] = f"Bearer {endpoint.api_key}"
        self._http = httpx.AsyncClient(
            base_url=endpoint.base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=30.0),
            limits=httpx.Limits(max_connections=256, max_keepalive_connections=64),
        )

    async def __aenter__(self) -> ChatClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _pace(self) -> None:
        if self._interval <= 0:
            return
        async with self._pace_lock:
            now = time.monotonic()
            wait = self._next_start - now
            # Jitter keeps request starts from forming a machine-regular pattern.
            self._next_start = max(now, self._next_start) + self._interval * random.uniform(
                0.5, 1.5
            )
        if wait > 0:
            await asyncio.sleep(wait)

    async def chat(self, req: Request, *, thinking_off: bool = True) -> Completion:
        body = req.body(self.endpoint, thinking_off=thinking_off)
        async with self._sem:
            attempt = 0
            while True:
                attempt += 1
                await self._pace()
                result, retry_after = await self._once(body)
                result.attempts = attempt
                retryable = result.error is not None and (
                    result.status is None or result.status in RETRY_STATUS
                )
                if not retryable or attempt > self.max_retries:
                    return result
                backoff = retry_after or min(60.0, 2.0**attempt) * random.uniform(0.75, 1.25)
                await asyncio.sleep(backoff)

    async def _once(self, body: dict[str, Any]) -> tuple[Completion, float | None]:
        c = Completion(started_at=time.time())
        t0 = time.perf_counter()
        text: list[str] = []
        reasoning: list[str] = []
        logprobs: list[list[Any]] = []
        try:
            async with self._http.stream("POST", "/chat/completions", json=body) as resp:
                c.status = resp.status_code
                if resp.status_code != 200:
                    raw = (await resp.aread()).decode(errors="replace")
                    c.error = f"HTTP {resp.status_code}: {raw[:300]}"
                    ra = resp.headers.get("retry-after")
                    return c, float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    c.chunks += 1
                    if err := chunk.get("error"):
                        c.error = f"stream error: {str(err)[:300]}"
                        break
                    c.served_model = chunk.get("model") or c.served_model
                    if usage := chunk.get("usage"):
                        c.prompt_tokens = usage.get("prompt_tokens")
                        c.completion_tokens = usage.get("completion_tokens")
                        details = usage.get("prompt_tokens_details") or {}
                        cached = details.get("cached_tokens", usage.get("prompt_cache_hit_tokens"))
                        if cached is not None:
                            c.cached_tokens = int(cached)
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        r = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        t = delta.get("content") or ""
                        now = time.perf_counter() - t0
                        if (r or t) and c.ttft_s is None:
                            c.ttft_s = now
                        if t and c.ttfc_s is None:
                            c.ttfc_s = now
                        reasoning.append(r)
                        text.append(t)
                        logprobs += _parse_logprobs(choice)
                        if fr := choice.get("finish_reason"):
                            c.finish_reason = fr
        except httpx.HTTPError as e:
            c.error = f"{type(e).__name__}: {e}"[:300]
        c.latency_s = time.perf_counter() - t0
        c.text = "".join(text)
        c.reasoning = "".join(reasoning)
        c.logprobs = logprobs or None
        if c.error is None and c.chunks == 0:
            c.error = "empty response"
        return c, None
