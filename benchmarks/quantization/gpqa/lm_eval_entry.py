"""
Patch Anthropic Messages parsing for DashScope (content may include thinking blocks), then run lm-eval CLI.

Used by ``run_gpqa_diamond.py`` in this directory (not ``python -m lm_eval`` directly).

Readable per-question flow on stderr when ``GPQA_DEBUG`` is unset or truthy (``0`` / ``false`` / ``no`` turns it off).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _debug_on() -> bool:
    v = os.environ.get("GPQA_DEBUG", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _dlog(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- GPQA one-flow debug (TemplateAPI hooks; only active during generate_until) ---

_orig_generate_until: Any = None
_orig_model_call: Any = None

_active_flow: bool = False
_ctx_to_doc: dict[str, dict[str, Any]] = {}
_flow_total: int = 0
_last_ctx_key: str | None = None
_q_index: int = 0


def _reset_flow_state(total: int) -> None:
    global _last_ctx_key, _q_index, _flow_total
    _last_ctx_key = None
    _q_index = 0
    _flow_total = total


def _serialize_ctx(ctx: Any) -> str | None:
    """Stable key for Instance.args[0] and the same value passed to model_call (messages[0])."""
    if ctx is None:
        return None
    if isinstance(ctx, str):
        return ctx
    try:
        from lm_eval.models.api_models import JsonChatStr

        if isinstance(ctx, JsonChatStr):
            return str(ctx.prompt)
    except Exception:
        pass
    if isinstance(ctx, (list, dict, tuple)):
        return json.dumps(ctx, sort_keys=True, ensure_ascii=False, default=str)
    return str(ctx)


def _build_ctx_to_doc(requests: list) -> dict[str, dict[str, Any]]:
    m: dict[str, dict[str, Any]] = {}
    for inst in requests:
        ctx = inst.args[0]
        key = _serialize_ctx(ctx)
        if key is not None and key not in m:
            m[key] = inst.doc
    return m


def _messages_lookup_key(messages: Any) -> str | None:
    if not messages:
        return None
    if isinstance(messages, str):
        return messages
    first = messages[0]
    return _serialize_ctx(first)


def _extract_gpqa_choice(text: str) -> str | None:
    """Best-effort match to gpqa_diamond_cot_zeroshot CoT filters (strict then fallback)."""
    if not text or not text.strip():
        return None
    m = re.search(r"The answer is\s*(\([^)]+\))", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip().upper()
    found = re.findall(r"\([A-D]\)", text, flags=re.IGNORECASE)
    if found:
        return found[-1].strip().upper()
    return None


def _verdict(pred: str | None, gold: str | None) -> str:
    if not gold:
        return "UNKNOWN (no gold in doc map)"
    if pred is None:
        return "WRONG (unparseable model answer)"
    g = gold.strip().upper()
    p = pred.strip().upper()
    if p == g:
        return "RIGHT"
    return "WRONG"


def _wrap_template_generate_until() -> None:
    global _orig_generate_until, _active_flow, _ctx_to_doc
    from lm_eval.models.api_models import TemplateAPI

    if _orig_generate_until is None:
        _orig_generate_until = TemplateAPI.generate_until

    def wrapped(self, requests, disable_tqdm: bool = False):  # noqa: ANN001
        global _active_flow, _ctx_to_doc
        if not _debug_on():
            return _orig_generate_until(self, requests, disable_tqdm=disable_tqdm)
        if not requests:
            return _orig_generate_until(self, requests, disable_tqdm=disable_tqdm)
        _active_flow = True
        _ctx_to_doc = _build_ctx_to_doc(list(requests))
        n = len(requests)
        _reset_flow_state(n)
        _dlog("")
        _dlog("--- GPQA eval flow ---")
        _dlog(f"batch: {n} question(s) (expecting one LLM round-trip each)")
        try:
            return _orig_generate_until(self, requests, disable_tqdm=disable_tqdm)
        finally:
            _dlog("--- end GPQA eval flow ---")
            _dlog("")
            _active_flow = False
            _ctx_to_doc = {}

    TemplateAPI.generate_until = wrapped  # type: ignore[method-assign]


def _wrap_template_model_call() -> None:
    global _orig_model_call, _q_index, _last_ctx_key
    from lm_eval.models.api_models import TemplateAPI

    if _orig_model_call is None:
        _orig_model_call = TemplateAPI.model_call

    def wrapped(  # noqa: ANN001
        self,
        messages,
        *,
        generate: bool = True,
        gen_kwargs: dict | None = None,
        **kwargs: Any,
    ):
        global _q_index, _last_ctx_key
        if not _debug_on() or not generate or not _active_flow:
            return _orig_model_call(
                self,
                messages,
                generate=generate,
                gen_kwargs=gen_kwargs,
                **kwargs,
            )

        ctx_key = _messages_lookup_key(messages)
        doc = _ctx_to_doc.get(ctx_key) if ctx_key else None
        gold = (doc or {}).get("answer")

        if ctx_key is not None and ctx_key != _last_ctx_key:
            _last_ctx_key = ctx_key
            _q_index += 1
        i = _q_index
        n = _flow_total
        prompt_chars = len(ctx_key) if ctx_key else 0

        _dlog(f"Q {i}/{n} | gold (letter) = {gold!r}")
        _dlog(f"Q {i}/{n} | question sent ({prompt_chars} chars in prompt)")
        _dlog(f"Q {i}/{n} | waiting for LLM response …")

        t0 = time.perf_counter()
        out = _orig_model_call(
            self,
            messages,
            generate=generate,
            gen_kwargs=gen_kwargs,
            **kwargs,
        )
        dt = time.perf_counter() - t0

        if out is None:
            _dlog(f"Q {i}/{n} | received: FAILED after {dt:.1f}s (no JSON body)")
            return out

        try:
            texts = self.parse_generations(outputs=out, contexts=None)
            raw_text = "".join(texts) if isinstance(texts, list) else str(texts)
        except Exception as e:  # noqa: BLE001
            raw_text = ""
            _dlog(f"Q {i}/{n} | parse_generations error: {e!r}")

        pred = _extract_gpqa_choice(raw_text)
        verdict = _verdict(pred, gold)
        preview = (raw_text.replace("\n", " ").strip())[:240]
        if len(raw_text) > 240:
            preview += " …"

        _dlog(
            f"Q {i}/{n} | received: {len(raw_text)} chars in {dt:.1f}s | "
            f"parsed={pred!r} → {verdict}"
        )
        if preview:
            _dlog(f"Q {i}/{n} | model text (preview): {preview}")

        return out

    TemplateAPI.model_call = wrapped  # type: ignore[method-assign]


def _patch_gpqa_debug_flow() -> None:
    if not _debug_on():
        return
    _wrap_template_generate_until()
    _wrap_template_model_call()


def _patch_anthropic_parse() -> None:
    from lm_eval.models import anthropic_llms as m

    def parse_generations(self, outputs, **kwargs):  # noqa: ANN001
        res: list[str] = []
        if not isinstance(outputs, list):
            outputs = [outputs]
        for out in outputs:
            parts: list[str] = []
            for block in out.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and "text" in block:
                    parts.append(block["text"])
            res.append("".join(parts))
        return res

    m.AnthropicChat.parse_generations = parse_generations  # type: ignore[method-assign]


def main() -> None:
    _patch_gpqa_debug_flow()
    _patch_anthropic_parse()
    from lm_eval.__main__ import cli_evaluate

    cli_evaluate()


if __name__ == "__main__":
    main()
