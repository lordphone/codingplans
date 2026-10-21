"""Stealth-friendly OpenAI-compatible chat client for fidelity benchmarks.

Runs compare a coding-plan endpoint against the model vendor's official API.
A provider optimizing cost may watch inbound traffic for audit patterns
(identical prompts hammered back-to-back, suspicious user agents,
zero think-time, perfectly periodic requests). This client is the shared
mitigation layer — those signals stay hidden here:

  * One HTTP request in flight at a time. No batch API, no parallel calls.
  * Streaming chat completions (matches what real IDE clients do — Cursor,
    Claude Code, Codex, Copilot all stream).
  * A single rotated IDE-flavored User-Agent per session, plus matching
    secondary headers when the IDE sends them, so all calls in one audit
    look like one developer in one tool.
  * Randomized think-time pause between calls (uniform in [min, max]) so
    request timing has the burstiness of a real coding session.

The weight-signal benchmarks also shuffle prompt × side × sample order across
their schedule (see common.make_schedule), which together with the per-call
pause reads on the wire like a developer poking at unrelated questions.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "StealthChatClient",
]


# ---------------------------------------------------------------------------
# IDE-flavored client header profiles
# ---------------------------------------------------------------------------
#
# Pulled from the same set used by benchmarks/performance/scenarios.py so the
# fidelity traffic blends in with the existing TPS traffic. We pick one
# profile per StealthChatClient instance — i.e. one profile per audit run —
# because real IDE sessions don't change their User-Agent mid-session.

# Sent instead of a rotated profile to endpoints flagged `honest_user_agent`
# (plans whose terms treat a modified User-Agent as a violation).
HONEST_USER_AGENT = "codingplans-audit/1.0 (+https://github.com/lordphone/codingplans)"

_CLIENT_PROFILES: tuple[dict[str, str], ...] = (
    {
        "User-Agent": "connect-es/1.6.1",
    },
    {
        "User-Agent": "claude-cli/2.1.90 (external, cli)",
    },
    {
        "User-Agent": "codex-cli/1.0.3",
    },
    {
        "User-Agent": "opencode/1.2.15",
    },
    {
        "User-Agent": "GitHubCopilotChat/0.37.2026011603",
        "Editor-Version": "vscode/1.98.0",
    },
)


@dataclass(frozen=True)
class ChatRequest:
    """One chat completion request, agnostic to the endpoint it targets.

    `messages` is the standard OpenAI chat array. `extra_params` is merged
    on top of the request body so individual tests can pass things like
    `top_p` or provider-specific flags without the client knowing about
    them. Endpoint-level `extra_params` (see targets.Endpoint) is merged
    first, then per-call `extra_params` wins on conflict.
    """

    messages: tuple[dict[str, Any], ...]
    temperature: float
    max_tokens: int
    extra_params: dict[str, Any] | None = None
    # OpenAI-format tool definitions; omitted from the body when None.
    tools: tuple[dict[str, Any], ...] | None = None
    # True/False merges the endpoint's thinking_on/thinking_off params;
    # None leaves the endpoint's default behavior alone.
    thinking: bool | None = None


@dataclass
class ChatResponse:
    """Result of one streamed completion. `content` is the concatenated
    visible answer; reasoning/thinking deltas are kept apart in `reasoning`
    so the text-comparison tests only ever see the user-visible answer.

    The trailing fields default to empty so older call sites that build a
    ChatResponse by hand (tests, fixtures) keep working."""

    content: str
    completion_tokens: int | None
    finish_reason: str | None
    latency_s: float
    reasoning: str = ""
    prompt_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    # Assembled tool calls: [{"id", "name", "arguments"}] with `arguments`
    # the raw (possibly malformed) JSON string exactly as streamed.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    ttft_s: float | None = None
    response_id: str | None = None
    served_model: str | None = None


def _delta_reasoning(delta: dict[str, Any]) -> str | None:
    """Return the reasoning/thinking piece of an SSE delta, if any.
    Vendors disagree on the field name (`reasoning_content` for DeepSeek /
    Qwen / GLM / Kimi, `reasoning` for OpenRouter-style gateways)."""
    for key in ("reasoning_content", "reasoning"):
        r = delta.get(key)
        if isinstance(r, str) and r:
            return r
    return None


def _usage_int(usage: dict[str, Any], *path: str) -> int | None:
    cur: Any = usage
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur if isinstance(cur, int) else None


def _delta_content(delta: dict[str, Any]) -> str | None:
    """Return only the visible-content piece of an SSE delta.

    Reasoning / thinking deltas (`reasoning_content`, `reasoning`) are
    intentionally ignored — they'd confound the inter-side text comparisons
    these fidelity tests rely on."""
    c = delta.get("content")
    if isinstance(c, str) and c:
        return c
    return None


class StealthChatClient:
    """Sequential, header-rotated chat client.

    Use as a context manager so the underlying httpx.Client is closed
    cleanly on the way out:

        with StealthChatClient(min_sleep_s=1.0, max_sleep_s=4.0) as client:
            for call in schedule:
                resp = client.chat(endpoint, request)
                client.pause()

    The client rotates its IDE-style headers exactly once, at construction
    time. That keeps every call in one audit looking like one developer
    in one editor session.
    """

    def __init__(
        self,
        *,
        min_sleep_s: float = 1.0,
        max_sleep_s: float = 4.0,
        connect_timeout_s: float = 15.0,
        read_timeout_s: float = 180.0,
        seed: int | None = None,
    ) -> None:
        if min_sleep_s < 0 or max_sleep_s < 0:
            raise ValueError("sleep bounds must be non-negative")
        if max_sleep_s < min_sleep_s:
            raise ValueError("max_sleep_s must be >= min_sleep_s")
        self._min_sleep = float(min_sleep_s)
        self._max_sleep = float(max_sleep_s)
        self._rng = random.Random(seed)
        self._headers = dict(self._rng.choice(_CLIENT_PROFILES))
        self._client = httpx.Client(
            timeout=httpx.Timeout(read_timeout_s, connect=connect_timeout_s),
            headers={"Accept": "text/event-stream"},
        )

    # ------------------------------------------------------------------ ctx
    def __enter__(self) -> "StealthChatClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — close should never raise
            pass

    # ---------------------------------------------------------------- public
    @property
    def session_user_agent(self) -> str:
        return self._headers.get("User-Agent", "")

    def pause(self) -> None:
        """Sleep a random uniform interval inside the configured range.

        Called between calls by every fidelity driver. Approximates a real
        developer reading the previous answer before sending the next prompt.
        """
        if self._max_sleep <= 0:
            return
        time.sleep(self._rng.uniform(self._min_sleep, self._max_sleep))

    def chat(self, endpoint, request: ChatRequest, *, allow_empty: bool = False) -> ChatResponse:
        """Issue one streamed chat completion against `endpoint`.

        Raises on transport errors, non-2xx responses, or empty completions.
        `allow_empty=True` returns instead of raising when the stream carried
        no visible content — tests that measure truncation (a reasoning model
        that spends all of max_tokens thinking) need to record that outcome.
        Callers (test drivers) wrap this in try/except so one bad
        call doesn't kill a whole panel.
        """
        api_key = endpoint.api_key()
        if not api_key:
            raise RuntimeError(
                f"{endpoint.api_key_env} not set in env (needed for {endpoint.label})"
            )

        url = endpoint.base_url.rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": endpoint.model,
            "messages": [dict(m) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            body["tools"] = [dict(t) for t in request.tools]
        if endpoint.extra_params:
            body.update(endpoint.extra_params)
        if request.thinking is True and getattr(endpoint, "thinking_on", None):
            body.update(endpoint.thinking_on)
        elif request.thinking is False and getattr(endpoint, "thinking_off", None):
            body.update(endpoint.thinking_off)
        if request.extra_params:
            body.update(request.extra_params)

        headers = dict(self._headers)
        if getattr(endpoint, "honest_user_agent", False):
            headers = {"User-Agent": HONEST_USER_AGENT}
        headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"

        chunks: list[str] = []
        reasoning_chunks: list[str] = []
        completion_tokens: int | None = None
        prompt_tokens: int | None = None
        reasoning_tokens: int | None = None
        cached_tokens: int | None = None
        response_id: str | None = None
        served_model: str | None = None
        tool_parts: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        first_token_at: float | None = None
        first_content_at: float | None = None
        last_any_at: float | None = None
        last_content_at: float | None = None
        started = time.perf_counter()

        with self._client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                # Drain a short error body for the exception message.
                resp.read()
                snippet = (resp.text or "")[:400]
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code} from {endpoint.label}: {snippet}",
                    request=resp.request,
                    response=resp,
                )

            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                else:
                    continue
                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if response_id is None and isinstance(chunk.get("id"), str):
                    response_id = chunk["id"]
                if served_model is None and isinstance(chunk.get("model"), str):
                    served_model = chunk["model"]

                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    ct = usage.get("completion_tokens")
                    if isinstance(ct, int):
                        completion_tokens = ct
                    pt = usage.get("prompt_tokens")
                    if isinstance(pt, int):
                        prompt_tokens = pt
                    rt = _usage_int(usage, "completion_tokens_details", "reasoning_tokens")
                    if rt is not None:
                        reasoning_tokens = rt
                    cached = _usage_int(usage, "prompt_tokens_details", "cached_tokens")
                    if cached is None:
                        cached = _usage_int(usage, "cached_tokens")
                    if cached is not None:
                        cached_tokens = cached

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice0 = choices[0] or {}

                fr = choice0.get("finish_reason")
                if isinstance(fr, str) and fr:
                    finish_reason = fr

                delta = choice0.get("delta") or {}
                if not isinstance(delta, dict):
                    continue
                now = time.perf_counter()

                r_piece = _delta_reasoning(delta)
                if r_piece is not None:
                    if first_token_at is None:
                        first_token_at = now
                    reasoning_chunks.append(r_piece)
                    last_any_at = now

                for tc in delta.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    idx = tc.get("index", 0) if isinstance(tc.get("index"), int) else 0
                    part = tool_parts.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                    if isinstance(tc.get("id"), str) and tc["id"]:
                        part["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if isinstance(fn, dict):
                        if isinstance(fn.get("name"), str):
                            part["name"] += fn["name"]
                        if isinstance(fn.get("arguments"), str):
                            part["arguments"] += fn["arguments"]
                    if first_token_at is None:
                        first_token_at = now
                    last_content_at = now

                piece = _delta_content(delta)
                if piece is None:
                    continue
                if first_token_at is None:
                    first_token_at = now
                if first_content_at is None:
                    first_content_at = now
                last_content_at = now
                chunks.append(piece)

        tool_calls = [tool_parts[i] for i in sorted(tool_parts)]
        if last_content_at is None or (first_content_at is None and not tool_calls):
            if not allow_empty:
                raise RuntimeError(
                    f"No streamed content from {endpoint.label} (model={endpoint.model})"
                )
            last_content_at = last_any_at if last_any_at is not None else time.perf_counter()

        return ChatResponse(
            content="".join(chunks),
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
            latency_s=last_content_at - started,
            reasoning="".join(reasoning_chunks),
            prompt_tokens=prompt_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_tokens=cached_tokens,
            tool_calls=tool_calls,
            ttft_s=(first_token_at - started) if first_token_at is not None else None,
            response_id=response_id,
            served_model=served_model,
        )
