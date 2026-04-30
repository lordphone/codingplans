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
from dataclasses import dataclass
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

    messages: tuple[dict[str, str], ...]
    temperature: float
    max_tokens: int
    extra_params: dict[str, Any] | None = None


@dataclass
class ChatResponse:
    """Result of one streamed completion. `content` is the concatenated
    visible answer; reasoning/thinking deltas are dropped on purpose so the
    fidelity benchmarks compare only the user-visible text."""

    content: str
    completion_tokens: int | None
    finish_reason: str | None
    latency_s: float


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

    def chat(self, endpoint, request: ChatRequest) -> ChatResponse:
        """Issue one streamed chat completion against `endpoint`.

        Raises on transport errors, non-2xx responses, or empty completions.
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
        if endpoint.extra_params:
            body.update(endpoint.extra_params)
        if request.extra_params:
            body.update(request.extra_params)

        headers = dict(self._headers)
        headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"

        chunks: list[str] = []
        completion_tokens: int | None = None
        finish_reason: str | None = None
        first_content_at: float | None = None
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

                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    ct = usage.get("completion_tokens")
                    if isinstance(ct, int):
                        completion_tokens = ct

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
                piece = _delta_content(delta)
                if piece is None:
                    continue
                now = time.perf_counter()
                if first_content_at is None:
                    first_content_at = now
                last_content_at = now
                chunks.append(piece)

        if first_content_at is None or last_content_at is None:
            raise RuntimeError(
                f"No streamed content from {endpoint.label} (model={endpoint.model})"
            )

        return ChatResponse(
            content="".join(chunks),
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
            latency_s=last_content_at - started,
        )
