#!/usr/bin/env python3
"""Reasoning budget — is thinking disabled, truncated, or capped on the plan?

Thinking tokens are the most expensive tokens a provider serves, and they are
invisible to most users: a plan can quietly lower the reasoning effort, cap
the thinking budget, or route to a non-thinking variant, and the reply still
"looks" fine. Users of GLM coding plans reported exactly this ("shortened
thinking") in 2026.

Per sample we record whether any reasoning was streamed, its length (the
vendor's `reasoning_tokens` when reported, else characters), the total
completion tokens, the finish reason, and whether the final `ANSWER:` is
correct.

Comparator:
  * accuracy gap (two-proportion test)
  * reasoning length — permutation test on log(reasoning length) and the
    ratio of medians target/reference
  * thinking presence — share of samples with any reasoning at all
Fails when accuracy is significantly worse by >10pp, when the median
reasoning length is <60% of the reference's and significantly lower, or when
the reference thinks on ≥90% of samples and the target on <50%.

Requests are sent with `thinking=True`, which merges each endpoint's
`thinking.on` params from endpoints.json, and a generous max_tokens.

Usage:
  python benchmarks/fidelity/reasoning/test_reasoning_budget.py --endpoint glm5-official
"""

from __future__ import annotations

import math
import re
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
from reasoning_prompts import REASONING_PANEL_ID, REASONING_PROMPTS  # noqa: E402
from stats import permutation_test_mean, two_proportion_test  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "reasoning_budget"
DEFAULT_N_SAMPLES = 2
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_SLEEP_RANGE = (2.0, 6.0)
# Vendors force T≈1 in thinking mode anyway; asking for it keeps both sides
# on the same documented setting.
TEMPERATURE = 1.0

ALPHA = 0.05
ACCURACY_GAP_THRESHOLD = 0.10
LENGTH_RATIO_FLOOR = 0.60
MIN_SAMPLES_PER_SIDE = 20

_ANSWER_RE = re.compile(r"ANSWER:\s*\**\s*(-?[\d,]+)", re.IGNORECASE)


def parse_answer(content: str) -> int | None:
    found = _ANSWER_RE.findall(content or "")
    if not found:
        return None
    try:
        return int(found[-1].replace(",", ""))
    except ValueError:
        return None


def _record(item: PromptItem, resp: ChatResponse) -> dict[str, Any]:
    parsed = parse_answer(resp.content)
    reasoning_len = resp.reasoning_tokens if isinstance(resp.reasoning_tokens, int) else None
    return {
        "parsed": parsed,
        "correct": parsed == (item.meta or {}).get("expected"),
        "has_reasoning": bool(resp.reasoning) or bool(reasoning_len),
        "reasoning_chars": len(resp.reasoning),
        "reasoning_tokens": reasoning_len,
        "completion_tokens": resp.completion_tokens,
        "finish_reason": resp.finish_reason,
    }


def run_reasoning_budget(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = REASONING_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = None,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    return run_panel(
        endpoint,
        test_name=TEST_NAME,
        panel_id=REASONING_PANEL_ID,
        panel=panel,
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range=sleep_range,
        build_request=lambda item, _k: ChatRequest(
            messages=item.messages, temperature=TEMPERATURE, max_tokens=max_tokens,
            thinking=True,
        ),
        record=_record,
        allow_empty=True,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def reasoning_length(rec: dict) -> float | None:
    """Prefer vendor-reported reasoning tokens; fall back to characters / 4
    (both sides fall back the same way when neither reports)."""
    if isinstance(rec.get("reasoning_tokens"), int):
        return float(rec["reasoning_tokens"])
    chars = rec.get("reasoning_chars") or 0
    return chars / 4.0


@dataclass
class ReasoningBudgetReport:
    test_name: str
    reference_label: str
    target_label: str
    reference_samples: int
    target_samples: int
    reference_accuracy: float
    target_accuracy: float
    accuracy_gap_ref_minus_target: float
    accuracy_p_value: float
    reference_median_reasoning: float
    target_median_reasoning: float
    reasoning_ratio_target_over_ref: float
    reasoning_p_value: float
    reference_thinking_rate: float
    target_thinking_rate: float
    target_truncated_rate: float
    metric: str
    reference_value: float
    target_value: float
    p_value: float
    inconclusive: bool
    fail: bool


def compare_reasoning_budget(reference: RunResult, target: RunResult) -> ReasoningBudgetReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)
    ref = [r for p in reference.prompts for r in p.records]
    tgt = [r for p in target.prompts for r in p.records]

    r_ok, t_ok = sum(r["correct"] for r in ref), sum(r["correct"] for r in tgt)
    acc_gap, acc_p = two_proportion_test(r_ok, len(ref), t_ok, len(tgt))

    r_len = [x for x in (reasoning_length(r) for r in ref) if x is not None]
    t_len = [x for x in (reasoning_length(r) for r in tgt) if x is not None]
    r_med = float(median(r_len)) if r_len else 0.0
    t_med = float(median(t_len)) if t_len else 0.0
    ratio = t_med / r_med if r_med > 0 else 1.0
    _, len_p = permutation_test_mean(
        [math.log1p(x) for x in r_len], [math.log1p(x) for x in t_len]
    ) if (r_len and t_len) else (0.0, 1.0)

    r_think = sum(r["has_reasoning"] for r in ref) / len(ref) if ref else 0.0
    t_think = sum(r["has_reasoning"] for r in tgt) / len(tgt) if tgt else 0.0
    t_trunc = sum(r.get("finish_reason") == "length" for r in tgt) / len(tgt) if tgt else 0.0

    inconclusive = min(len(ref), len(tgt)) < MIN_SAMPLES_PER_SIDE
    bonf = ALPHA / 2
    fail = (not inconclusive) and (
        (acc_gap > ACCURACY_GAP_THRESHOLD and acc_p < bonf)
        or (ratio < LENGTH_RATIO_FLOOR and len_p < bonf)
        or (r_think >= 0.9 and t_think < 0.5)
    )
    r_acc = r_ok / len(ref) if ref else 0.0
    t_acc = t_ok / len(tgt) if tgt else 0.0
    return ReasoningBudgetReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        reference_samples=len(ref),
        target_samples=len(tgt),
        reference_accuracy=round(r_acc, 4),
        target_accuracy=round(t_acc, 4),
        accuracy_gap_ref_minus_target=round(acc_gap, 4),
        accuracy_p_value=acc_p,
        reference_median_reasoning=round(r_med, 1),
        target_median_reasoning=round(t_med, 1),
        reasoning_ratio_target_over_ref=round(ratio, 4),
        reasoning_p_value=len_p,
        reference_thinking_rate=round(r_think, 4),
        target_thinking_rate=round(t_think, 4),
        target_truncated_rate=round(t_trunc, 4),
        metric="median_reasoning_tokens",
        reference_value=round(r_med, 1),
        target_value=round(t_med, 1),
        p_value=min(1.0, 2 * min(acc_p, len_p)),
        inconclusive=inconclusive,
        fail=fail,
    )


def main() -> int:
    return standard_cli(
        description=__doc__.splitlines()[0],
        test_name=TEST_NAME,
        panel=REASONING_PROMPTS,
        run=run_reasoning_budget,
        runs_dir=RUNS_DIR,
        default_n=DEFAULT_N_SAMPLES,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        default_sleep=DEFAULT_SLEEP_RANGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
