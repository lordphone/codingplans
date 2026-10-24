"""A toy OpenAI-compatible model server for offline tests.

It is not a language model; it is just enough of one for every probe to have
a known right answer and a known way to be degraded:

  * answers "What is a × b?" (and gets a configurable share wrong),
  * finds access codes in needle documents (and forgets past `context_cap`),
  * samples short answers from a prompt-seeded distribution (which
    `noise` perturbs, standing in for quantization), with top-k logprobs,
  * reports usage with a word-based tokenizer (`inject_tokens` adds a hidden
    surplus) and simulates prefill time with an optional prefix cache.

Used by tests/ and by `planaudit selftest`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

VOCAB = [
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
    "kilo",
    "lima",
]


@dataclass
class Behaviour:
    noise: float = 0.0  # perturbation of answer distributions (0 = honest)
    wrong_rate: float = 0.0  # extra share of arithmetic answers that are wrong
    context_cap: int | None = None  # tokens; needles beyond are forgotten
    inject_tokens: int = 0  # hidden prompt surplus
    prefix_cache: bool = True
    report_cache: bool = True
    prefill_s_per_1k: float = 0.01
    seed: int = 0
    _cache: set[str] = field(default_factory=set)


def _h(*parts: object) -> int:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _tokens(text: str) -> int:
    return math.ceil(len(text.split()) * 1.3) + 4


def _dist(prompt: str, b: Behaviour) -> list[float]:
    r = random.Random(_h("dist", prompt))
    logits = [r.gauss(0, 1.5) for _ in VOCAB]
    if b.noise:
        q = random.Random(_h("noise", prompt, b.seed))
        logits = [x + q.gauss(0, b.noise) for x in logits]
    m = max(logits)
    w = [math.exp(x - m) for x in logits]
    s = sum(w)
    return [x / s for x in w]


def respond(
    body: dict[str, Any], b: Behaviour
) -> tuple[str, list[list[Any]] | None, dict[str, Any], float]:
    msgs = body.get("messages", [])
    prompt = "\n".join(str(m.get("content", "")) for m in msgs)
    temperature = float(body.get("temperature", 1.0) or 0.0)
    r = random.Random() if temperature > 0 else random.Random(_h("greedy", prompt))
    n_prompt = _tokens(prompt) + b.inject_tokens

    if m := re.search(r"What is (\d+) × (\d+)\?", prompt):
        a, c = int(m.group(1)), int(m.group(2))
        digits = len(m.group(1))
        p_wrong = min(1.0, 0.04 * digits + b.wrong_rate)
        wrong = random.Random(_h("arith", a, c, b.seed if b.wrong_rate else 0)).random() < p_wrong
        text = str(a * c + (10 ** (digits - 1) if wrong else 0))
        lps = None
    elif m := re.search(r"access code for the (\w+ \w+) vault\?", prompt):
        doc_words = prompt.split()
        found = re.search(rf"The access code for the {m.group(1)} vault is (\d+)\.", prompt)
        text = "000000"
        if found:
            pos = len(prompt[: found.start()].split())
            if b.context_cap is None or (len(doc_words) - pos) * 1.3 < b.context_cap:
                text = found.group(1)
        lps = None
    else:
        probs = _dist(prompt, b)
        if temperature > 0:
            k = r.choices(range(len(VOCAB)), weights=probs)[0]
        else:
            k = max(range(len(VOCAB)), key=probs.__getitem__)
        text = VOCAB[k]
        lps = None
        if body.get("logprobs"):
            top = sorted(range(len(VOCAB)), key=lambda i: -probs[i])[: body.get("top_logprobs", 5)]
            lps = [[VOCAB[k], math.log(probs[k]), [[VOCAB[i], math.log(probs[i])] for i in top]]]

    key = hashlib.sha1(prompt[:2000].encode()).hexdigest()
    hit = b.prefix_cache and key in b._cache
    b._cache.add(key)
    cached = int(n_prompt * 0.9) if hit else 0
    prefill = b.prefill_s_per_1k * (n_prompt - cached) / 1000
    usage = {"prompt_tokens": n_prompt, "completion_tokens": max(1, _tokens(text) - 4)}
    if b.report_cache:
        usage["prompt_tokens_details"] = {"cached_tokens": cached}
    return text, lps, usage, prefill


def make_app(b: Behaviour, model: str = "fake-model") -> Starlette:
    async def chat(request: Request):
        body = await request.json()
        text, lps, usage, prefill = respond(body, b)
        max_tokens = int(body.get("max_tokens") or 1 << 30)
        words = text.split(" ")[:max_tokens]
        await asyncio.sleep(prefill)
        if not body.get("stream"):
            return JSONResponse(
                {
                    "model": model,
                    "choices": [{"message": {"content": " ".join(words)}, "finish_reason": "stop"}],
                    "usage": usage,
                }
            )

        async def gen():
            for k, w in enumerate(words):
                choice: dict[str, Any] = {"delta": {"content": (" " if k else "") + w}}
                if lps and k < len(lps):
                    tok, lp, top = lps[k]
                    choice["logprobs"] = {
                        "content": [
                            {
                                "token": tok,
                                "logprob": lp,
                                "top_logprobs": [{"token": t, "logprob": v} for t, v in top],
                            }
                        ]
                    }
                yield f"data: {json.dumps({'model': model, 'created': int(time.time()), 'choices': [choice]})}\n\n"
                await asyncio.sleep(0.001)
            done = {"model": model, "choices": [{"delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(done)}\n\n"
            yield f"data: {json.dumps({'model': model, 'choices': [], 'usage': usage})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    async def models(_: Request):
        return JSONResponse({"data": [{"id": model}]})

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat, methods=["POST"]),
            Route("/v1/models", models),
        ]
    )
