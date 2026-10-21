#!/usr/bin/env python3
"""Token accounting — hidden prompt injection & usage inflation.

Same weights ⇒ same tokenizer ⇒ the official API and an honest plan report
the same `usage.prompt_tokens` for byte-identical requests (modulo a small,
constant chat-template difference). Two dishonest patterns show up as a
linear relationship between the two:

  target_prompt_tokens ≈ intercept + slope × reference_prompt_tokens

  * intercept ≫ 0 — the plan prepends a hidden system prompt (it shrinks
    your effective context, changes behavior, and you're billed for it).
  * slope > 1     — prompt tokens are inflated proportionally (quota burns
    faster than advertised), or a different (worse) tokenizer is in use,
    which itself means a different model.

We also compare *completion* accounting: tokens reported per visible output
character (content + reasoning). A higher ratio on the target means
completions are over-counted.

Max tokens is tiny (we only need usage), and every call is T=0.

Usage:
  python benchmarks/fidelity/integrity/test_token_accounting.py --endpoint glm5-official
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
_FIDELITY_DIR = _HERE.parent
for _p in (_FIDELITY_DIR, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from framework import (  # noqa: E402
    ChatRequest,
    ChatResponse,
    Endpoint,
    PromptItem,
    RunResult,
    assert_comparable,
    run_panel,
    standard_cli,
)
from integrity_prompts import TOKEN_ACCOUNTING_PANEL_ID, TOKEN_ACCOUNTING_PROMPTS  # noqa: E402
from stats import permutation_test_mean  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "token_accounting"
DEFAULT_N_SAMPLES = 3
DEFAULT_MAX_TOKENS = 32
DEFAULT_SLEEP_RANGE = (1.0, 4.0)

# A chat-template difference between two honest deployments is a handful of
# tokens; anything past this is a prompt nobody asked for.
INTERCEPT_THRESHOLD_TOKENS = 40.0
SLOPE_THRESHOLD = 1.03
COMPLETION_RATIO_THRESHOLD = 1.15
ALPHA = 0.05
MIN_PROMPTS_WITH_USAGE = 4


def _record(_item: PromptItem, resp: ChatResponse) -> dict[str, Any]:
    visible_chars = len(resp.content) + len(resp.reasoning)
    return {
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
        "reasoning_tokens": resp.reasoning_tokens,
        "cached_tokens": resp.cached_tokens,
        "visible_chars": visible_chars,
        "finish_reason": resp.finish_reason,
    }


def run_token_accounting(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = TOKEN_ACCOUNTING_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = None,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    return run_panel(
        endpoint,
        test_name=TEST_NAME,
        panel_id=TOKEN_ACCOUNTING_PANEL_ID,
        panel=panel,
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range=sleep_range,
        build_request=lambda item, _k: ChatRequest(
            messages=item.messages, temperature=0.0, max_tokens=max_tokens
        ),
        record=_record,
        allow_empty=True,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """Ordinary least squares y = a + b·x. Returns (intercept, slope)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my - mx, 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - slope * mx, slope


@dataclass
class TokenAccountingPrompt:
    prompt_idx: int
    name: str
    reference_prompt_tokens: float | None
    target_prompt_tokens: float | None
    surplus_tokens: float | None


@dataclass
class TokenAccountingReport:
    test_name: str
    reference_label: str
    target_label: str
    prompts_with_usage: int
    intercept_tokens: float
    slope: float
    median_surplus_tokens: float
    reference_completion_tokens_per_char: float
    target_completion_tokens_per_char: float
    completion_ratio_target_over_ref: float
    completion_p_value: float
    target_reports_usage: bool
    metric: str
    reference_value: float
    target_value: float
    p_value: float | None
    inconclusive: bool
    fail: bool
    per_prompt: list[TokenAccountingPrompt]


def _median_field(records: list[dict], key: str) -> float | None:
    vals = [r[key] for r in records if isinstance(r.get(key), int)]
    return float(median(vals)) if vals else None


def _per_char(records: list[dict]) -> list[float]:
    out = []
    for r in records:
        ct, chars = r.get("completion_tokens"), r.get("visible_chars") or 0
        if isinstance(ct, int) and ct > 0 and chars >= 8:
            out.append(ct / chars)
    return out


def compare_token_accounting(reference: RunResult, target: RunResult) -> TokenAccountingReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)
    by_tgt = {p.prompt_idx: p for p in target.prompts}
    per_prompt: list[TokenAccountingPrompt] = []
    xs: list[float] = []
    ys: list[float] = []
    ref_ratio: list[float] = []
    tgt_ratio: list[float] = []
    target_has_usage = False
    for rp in sorted(reference.prompts, key=lambda p: p.prompt_idx):
        tp = by_tgt.get(rp.prompt_idx)
        if tp is None:
            continue
        r_pt = _median_field(rp.records, "prompt_tokens")
        t_pt = _median_field(tp.records, "prompt_tokens")
        target_has_usage = target_has_usage or t_pt is not None
        if r_pt is not None and t_pt is not None:
            xs.append(r_pt)
            ys.append(t_pt)
        ref_ratio.extend(_per_char(rp.records))
        tgt_ratio.extend(_per_char(tp.records))
        per_prompt.append(TokenAccountingPrompt(
            prompt_idx=rp.prompt_idx,
            name=rp.name,
            reference_prompt_tokens=r_pt,
            target_prompt_tokens=t_pt,
            surplus_tokens=(t_pt - r_pt) if (r_pt is not None and t_pt is not None) else None,
        ))

    inconclusive = len(xs) < MIN_PROMPTS_WITH_USAGE
    intercept, slope = linear_fit(xs, ys) if len(xs) >= 2 else (0.0, 1.0)
    surpluses = [y - x for x, y in zip(xs, ys)]
    med_surplus = float(median(surpluses)) if surpluses else 0.0

    ref_cpc = sum(ref_ratio) / len(ref_ratio) if ref_ratio else 0.0
    tgt_cpc = sum(tgt_ratio) / len(tgt_ratio) if tgt_ratio else 0.0
    ratio = tgt_cpc / ref_cpc if ref_cpc > 0 else 1.0
    _, comp_p = permutation_test_mean(tgt_ratio, ref_ratio) if (ref_ratio and tgt_ratio) else (0.0, 1.0)

    # Prompt-token accounting is deterministic (same bytes in, same count
    # out), so it gets a hard threshold rather than a significance test.
    fail = (not inconclusive) and (
        intercept > INTERCEPT_THRESHOLD_TOKENS
        or med_surplus > INTERCEPT_THRESHOLD_TOKENS
        or slope > SLOPE_THRESHOLD
        or (ratio > COMPLETION_RATIO_THRESHOLD and comp_p < ALPHA)
    )
    return TokenAccountingReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        prompts_with_usage=len(xs),
        intercept_tokens=round(intercept, 2),
        slope=round(slope, 4),
        median_surplus_tokens=round(med_surplus, 2),
        reference_completion_tokens_per_char=round(ref_cpc, 4),
        target_completion_tokens_per_char=round(tgt_cpc, 4),
        completion_ratio_target_over_ref=round(ratio, 4),
        completion_p_value=comp_p,
        target_reports_usage=target_has_usage,
        metric="median_prompt_token_surplus",
        reference_value=0.0,
        target_value=round(med_surplus, 2),
        p_value=None,
        inconclusive=inconclusive,
        fail=fail,
        per_prompt=per_prompt,
    )


def main() -> int:
    return standard_cli(
        description=__doc__.splitlines()[0],
        test_name=TEST_NAME,
        panel=TOKEN_ACCOUNTING_PROMPTS,
        run=run_token_accounting,
        runs_dir=RUNS_DIR,
        default_n=DEFAULT_N_SAMPLES,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        default_sleep=DEFAULT_SLEEP_RANGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
