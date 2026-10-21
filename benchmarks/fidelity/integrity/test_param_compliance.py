#!/usr/bin/env python3
"""Parameter compliance — are request parameters actually honored?

Gateways that rewrite requests (to cap cost, to route to a different
backend, or because they only half-implement the OpenAI protocol) silently
drop parameters. Coding agents depend on several of them:

  max_tokens       the reply must stop at the cap with finish_reason=length
  stop             the stop string must never appear in the output
  response_format  json_object mode must return parseable JSON
  output cap       a ~10k-token reply requested with max_tokens=16000 must
                   not be cut short (a silently clamped max_tokens)
  temperature      T=1 must be measurably more diverse than T=0 (a backend
                   that pins temperature, or serves cached text, is flat)

Each panel item is one probe; its parameters live in `meta`. The comparator
reports compliance per probe on both sides and fails when the target is
significantly less compliant than the official API, or when the target's
temperature sensitivity collapses relative to the reference.

Usage:
  python benchmarks/fidelity/integrity/test_param_compliance.py --endpoint glm5-official
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
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
    normalize_text,
    run_panel,
    standard_cli,
)
from integrity_prompts import PARAM_PANEL_ID, PARAM_PROMPTS  # noqa: E402
from stats import two_proportion_test  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "param_compliance"
DEFAULT_N_SAMPLES = 8
DEFAULT_MAX_TOKENS = 256
DEFAULT_SLEEP_RANGE = (1.0, 4.0)

ALPHA = 0.05
COMPLIANCE_GAP_THRESHOLD = 0.10
# Reference must show at least this much T=1-vs-T=0 diversity for the
# temperature probe to be meaningful at all.
MIN_REF_TEMPERATURE_SENSITIVITY = 0.25
MIN_SAMPLES_PER_SIDE = 15


def check_probe(meta: dict[str, Any], resp: ChatResponse) -> bool | None:
    """True/False when the probe is pass/fail-scorable, None for the
    temperature probe (scored on the distribution, not per sample)."""
    probe = meta.get("probe")
    if probe == "max_tokens":
        limit = int(meta["max_tokens"])
        if resp.finish_reason != "length":
            return False
        if isinstance(resp.completion_tokens, int):
            # Reasoning tokens count toward the cap too; one token of slack
            # for vendors that count the terminal token.
            return resp.completion_tokens <= limit + 1
        # No usage reported: a token is rarely more than ~8 characters.
        return len(resp.content) + len(resp.reasoning) <= limit * 8
    if probe == "stop":
        return str(meta["forbidden"]) not in resp.content
    if probe == "output_cap":
        nums = re.findall(r"\d+", resp.content[-200:])
        return bool(nums) and int(nums[-1]) >= int(meta["last"]) - 5
    if probe == "json_mode":
        try:
            json.loads(resp.content)
        except (json.JSONDecodeError, ValueError):
            return False
        return True
    return None


def _build(default_max_tokens: int):
    def build(item: PromptItem, _k: int) -> ChatRequest:
        meta = item.meta or {}
        extra: dict[str, Any] = {}
        probe = meta.get("probe")
        if probe == "stop":
            extra["stop"] = list(meta["stop"])
        if probe == "json_mode":
            extra["response_format"] = {"type": "json_object"}
        return ChatRequest(
            messages=item.messages,
            temperature=float(meta.get("temperature", 0.0)),
            max_tokens=int(meta.get("max_tokens", default_max_tokens)),
            extra_params=extra or None,
        )
    return build


def _record(item: PromptItem, resp: ChatResponse) -> dict[str, Any]:
    return {
        "probe": (item.meta or {}).get("probe"),
        "compliant": check_probe(item.meta or {}, resp),
        "completion_tokens": resp.completion_tokens,
        "finish_reason": resp.finish_reason,
        "normalized": normalize_text(resp.content).strip().casefold()[:120],
        "visible_chars": len(resp.content),
    }


def run_param_compliance(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = PARAM_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = None,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    return run_panel(
        endpoint,
        test_name=TEST_NAME,
        panel_id=PARAM_PANEL_ID,
        panel=panel,
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range=sleep_range,
        build_request=_build(max_tokens),
        record=_record,
        allow_empty=True,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class ProbeComparison:
    probe: str
    reference_compliance: float
    target_compliance: float
    reference_n: int
    target_n: int
    p_value: float


@dataclass
class ParamComplianceReport:
    test_name: str
    reference_label: str
    target_label: str
    probes: list[ProbeComparison]
    reference_compliance: float
    target_compliance: float
    compliance_gap_ref_minus_target: float
    compliance_p_value: float
    reference_temperature_sensitivity: float
    target_temperature_sensitivity: float
    temperature_collapsed: bool
    metric: str
    reference_value: float
    target_value: float
    p_value: float
    inconclusive: bool
    fail: bool


def _distinct_ratio(records: list[dict]) -> float:
    vals = [r["normalized"] for r in records]
    return len(set(vals)) / len(vals) if vals else 0.0


def _temperature_sensitivity(run: RunResult) -> float:
    """Mean over low/high prompt pairs of distinct(T=1) − distinct(T=0).
    Pairs are matched by the user message they share."""
    lows: dict[str, list[dict]] = {}
    highs: dict[str, list[dict]] = {}
    for p in run.prompts:
        meta = p.meta or {}
        if meta.get("probe") != "temperature":
            continue
        key = p.name.replace("high", "").replace("low", "")
        (highs if float(meta.get("temperature", 0)) > 0 else lows)[key] = p.records
    deltas = [
        _distinct_ratio(highs[k]) - _distinct_ratio(lows[k])
        for k in highs if k in lows and highs[k] and lows[k]
    ]
    return sum(deltas) / len(deltas) if deltas else 0.0


def compare_param_compliance(reference: RunResult, target: RunResult) -> ParamComplianceReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)

    def by_probe(run: RunResult) -> dict[str, list[bool]]:
        out: dict[str, list[bool]] = {}
        for p in run.prompts:
            for r in p.records:
                if r.get("compliant") is not None:
                    out.setdefault(str(r["probe"]), []).append(bool(r["compliant"]))
        return out

    ref_bp, tgt_bp = by_probe(reference), by_probe(target)
    probes: list[ProbeComparison] = []
    for probe in sorted(set(ref_bp) | set(tgt_bp)):
        r, t = ref_bp.get(probe, []), tgt_bp.get(probe, [])
        _, p = two_proportion_test(sum(r), len(r), sum(t), len(t))
        probes.append(ProbeComparison(
            probe=probe,
            reference_compliance=round(sum(r) / len(r), 4) if r else 0.0,
            target_compliance=round(sum(t) / len(t), 4) if t else 0.0,
            reference_n=len(r),
            target_n=len(t),
            p_value=p,
        ))

    ref_all = [x for v in ref_bp.values() for x in v]
    tgt_all = [x for v in tgt_bp.values() for x in v]
    gap, p_all = two_proportion_test(sum(ref_all), len(ref_all), sum(tgt_all), len(tgt_all))
    ref_sens = _temperature_sensitivity(reference)
    tgt_sens = _temperature_sensitivity(target)
    collapsed = ref_sens >= MIN_REF_TEMPERATURE_SENSITIVITY and tgt_sens < ref_sens / 2

    inconclusive = min(len(ref_all), len(tgt_all)) < MIN_SAMPLES_PER_SIDE
    fail = (not inconclusive) and (
        (gap > COMPLIANCE_GAP_THRESHOLD and p_all < ALPHA) or collapsed
    )
    ref_rate = sum(ref_all) / len(ref_all) if ref_all else 0.0
    tgt_rate = sum(tgt_all) / len(tgt_all) if tgt_all else 0.0
    return ParamComplianceReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        probes=probes,
        reference_compliance=round(ref_rate, 4),
        target_compliance=round(tgt_rate, 4),
        compliance_gap_ref_minus_target=round(gap, 4),
        compliance_p_value=p_all,
        reference_temperature_sensitivity=round(ref_sens, 4),
        target_temperature_sensitivity=round(tgt_sens, 4),
        temperature_collapsed=collapsed,
        metric="parameter_compliance_rate",
        reference_value=round(ref_rate, 4),
        target_value=round(tgt_rate, 4),
        p_value=p_all,
        inconclusive=inconclusive,
        fail=fail,
    )


def main() -> int:
    return standard_cli(
        description=__doc__.splitlines()[0],
        test_name=TEST_NAME,
        panel=PARAM_PROMPTS,
        run=run_param_compliance,
        runs_dir=RUNS_DIR,
        default_n=DEFAULT_N_SAMPLES,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        default_sleep=DEFAULT_SLEEP_RANGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
