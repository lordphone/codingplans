#!/usr/bin/env python3
"""Tool-calling fidelity (single-endpoint runner + comparator).

Coding plans are consumed almost entirely through agents, and agents live or
die on tool calls. A deployment with a broken chat template, an aggressive
quantization, or a constrained-decoding shortcut usually still chats fine but
emits malformed arguments, forgets required fields, or stops calling tools
when it should (or calls them when it shouldn't). Moonshot's K2 Vendor
Verifier found exactly this across third-party Kimi K2 hosts.

Per sample we record:
  * triggered       — the response contained ≥1 tool call
  * schema_valid    — every call names a known tool and its arguments parse
                      as JSON and satisfy that tool's schema
  * decision_ok     — triggered matches the panel's expectation, a called
                      tool is in the allowed set, and parallel-call prompts
                      got at least `min_calls` calls

Comparator (reference vs target):
  * Schema accuracy (primary): valid calls / calls, two-proportion test.
  * Trigger similarity: 1 − mean over prompts of |trigger_rate_ref −
    trigger_rate_tgt| — the vendor verifier's headline agreement metric.
  * Decision accuracy: decision_ok rate, two-proportion test.
Fails when schema accuracy or decision accuracy is worse on the target by
more than its threshold AND significant at α=0.05 (Bonferroni over the two),
or when trigger similarity drops below 0.85.

Usage:
  python benchmarks/fidelity/agentic/test_tool_calls.py --endpoint kimi-k2.5-official
  python benchmarks/fidelity/agentic/test_tool_calls.py --endpoint kimi-k2.5-kimi-coding
  python benchmarks/fidelity/compare.py <ref>.summary.json <target>.summary.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
_FIDELITY_DIR = _HERE.parent
if str(_FIDELITY_DIR) not in sys.path:
    sys.path.insert(0, str(_FIDELITY_DIR))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

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
from schema_lite import validate  # noqa: E402
from stats import two_proportion_test  # noqa: E402
from tool_prompts import (  # noqa: E402
    TOOL_CALLS_PANEL_ID,
    TOOL_CALLS_PROMPTS,
    TOOL_CALLS_TEMPERATURE,
    TOOL_SCHEMAS,
    TOOLS,
)

RUNS_DIR = _HERE / "runs"

TEST_NAME = "tool_calls"
DEFAULT_N_SAMPLES = 5
DEFAULT_MAX_TOKENS = 1024
DEFAULT_SCHEDULE_SEED: int | None = None
DEFAULT_SLEEP_RANGE = (1.0, 4.0)

ALPHA = 0.05
SCHEMA_GAP_THRESHOLD = 0.03
DECISION_GAP_THRESHOLD = 0.08
TRIGGER_SIMILARITY_FLOOR = 0.85
MIN_SAMPLES_PER_SIDE = 30


def check_calls(tool_calls: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """Score one response's tool calls against the schemas and expectation.
    Pure: used by the runner to build records and by unit tests."""
    problems: list[str] = []
    names: list[str] = []
    for call in tool_calls:
        name = str(call.get("name") or "")
        names.append(name)
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            problems.append(f"unknown tool {name!r}")
            continue
        raw = call.get("arguments") or ""
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as e:
            problems.append(f"{name}: invalid JSON ({e.msg})")
            continue
        problems.extend(f"{name}: {p}" for p in validate(args, schema))

    triggered = bool(tool_calls)
    expect = meta.get("expect", "tool")
    if expect == "none":
        decision_ok = not triggered
    else:
        allowed = set(meta.get("allowed") or [])
        decision_ok = (
            triggered
            and (not allowed or all(n in allowed for n in names))
            and len(tool_calls) >= int(meta.get("min_calls", 1))
        )
    return {
        "triggered": triggered,
        "n_calls": len(tool_calls),
        "tool_names": names,
        "schema_valid": triggered and not problems,
        "schema_problems": problems[:5],
        "decision_ok": decision_ok,
    }


def _record(item: PromptItem, resp: ChatResponse) -> dict[str, Any]:
    rec = check_calls(resp.tool_calls, item.meta or {})
    rec["finish_reason"] = resp.finish_reason
    rec["raw_calls"] = [
        {"name": c.get("name"), "arguments": (c.get("arguments") or "")[:500]}
        for c in resp.tool_calls
    ]
    return rec


def run_tool_calls(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = TOOL_CALLS_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    def build(item: PromptItem, _sample_idx: int) -> ChatRequest:
        return ChatRequest(
            messages=item.messages,
            temperature=TOOL_CALLS_TEMPERATURE,
            max_tokens=max_tokens,
            tools=TOOLS,
        )

    return run_panel(
        endpoint,
        test_name=TEST_NAME,
        panel_id=TOOL_CALLS_PANEL_ID,
        panel=panel,
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range=sleep_range,
        build_request=build,
        record=_record,
        allow_empty=True,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class ToolCallPromptComparison:
    prompt_idx: int
    name: str
    expect: str
    reference_trigger_rate: float
    target_trigger_rate: float
    reference_decision_rate: float
    target_decision_rate: float
    target_schema_problems: list[str]


@dataclass
class ToolCallsReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    n_samples: int
    reference_samples: int
    target_samples: int
    reference_calls: int
    target_calls: int
    reference_schema_accuracy: float
    target_schema_accuracy: float
    schema_gap_ref_minus_target: float
    schema_p_value: float
    trigger_similarity: float
    reference_decision_accuracy: float
    target_decision_accuracy: float
    decision_gap_ref_minus_target: float
    decision_p_value: float
    # Uniform headline consumed by benchmarks/audit/run_audit.py.
    metric: str
    reference_value: float
    target_value: float
    p_value: float
    inconclusive: bool
    fail: bool
    per_prompt: list[ToolCallPromptComparison]


def _rate(xs: list[bool]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compare_tool_calls(reference: RunResult, target: RunResult) -> ToolCallsReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)
    by_ref = {p.prompt_idx: p for p in reference.prompts}
    by_tgt = {p.prompt_idx: p for p in target.prompts}

    ref_recs: list[dict] = []
    tgt_recs: list[dict] = []
    per_prompt: list[ToolCallPromptComparison] = []
    trigger_diffs: list[float] = []
    for idx in sorted(by_ref):
        rp, tp = by_ref[idx], by_tgt.get(idx)
        if tp is None:
            continue
        ref_recs.extend(rp.records)
        tgt_recs.extend(tp.records)
        r_trig = _rate([r["triggered"] for r in rp.records])
        t_trig = _rate([r["triggered"] for r in tp.records])
        if rp.records and tp.records:
            trigger_diffs.append(abs(r_trig - t_trig))
        problems = sorted({p for r in tp.records for p in r.get("schema_problems", [])})
        per_prompt.append(ToolCallPromptComparison(
            prompt_idx=idx,
            name=rp.name,
            expect=str((rp.meta or {}).get("expect", "tool")),
            reference_trigger_rate=round(r_trig, 4),
            target_trigger_rate=round(t_trig, 4),
            reference_decision_rate=round(_rate([r["decision_ok"] for r in rp.records]), 4),
            target_decision_rate=round(_rate([r["decision_ok"] for r in tp.records]), 4),
            target_schema_problems=problems[:5],
        ))

    ref_called = [r for r in ref_recs if r["triggered"]]
    tgt_called = [r for r in tgt_recs if r["triggered"]]
    ref_valid = sum(r["schema_valid"] for r in ref_called)
    tgt_valid = sum(r["schema_valid"] for r in tgt_called)
    schema_gap, schema_p = two_proportion_test(ref_valid, len(ref_called), tgt_valid, len(tgt_called))

    ref_dec = sum(r["decision_ok"] for r in ref_recs)
    tgt_dec = sum(r["decision_ok"] for r in tgt_recs)
    dec_gap, dec_p = two_proportion_test(ref_dec, len(ref_recs), tgt_dec, len(tgt_recs))

    trigger_similarity = 1.0 - (sum(trigger_diffs) / len(trigger_diffs)) if trigger_diffs else 0.0
    inconclusive = min(len(ref_recs), len(tgt_recs)) < MIN_SAMPLES_PER_SIDE
    bonferroni = ALPHA / 2
    fail = (not inconclusive) and (
        (schema_gap > SCHEMA_GAP_THRESHOLD and schema_p < bonferroni)
        or (dec_gap > DECISION_GAP_THRESHOLD and dec_p < bonferroni)
        or trigger_similarity < TRIGGER_SIMILARITY_FLOOR
    )
    ref_schema_acc = ref_valid / len(ref_called) if ref_called else 0.0
    tgt_schema_acc = tgt_valid / len(tgt_called) if tgt_called else 0.0
    return ToolCallsReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        n_samples=reference.n_samples,
        reference_samples=len(ref_recs),
        target_samples=len(tgt_recs),
        reference_calls=len(ref_called),
        target_calls=len(tgt_called),
        reference_schema_accuracy=round(ref_schema_acc, 4),
        target_schema_accuracy=round(tgt_schema_acc, 4),
        schema_gap_ref_minus_target=round(schema_gap, 4),
        schema_p_value=schema_p,
        trigger_similarity=round(trigger_similarity, 4),
        reference_decision_accuracy=round(_rate([r["decision_ok"] for r in ref_recs]), 4),
        target_decision_accuracy=round(_rate([r["decision_ok"] for r in tgt_recs]), 4),
        decision_gap_ref_minus_target=round(dec_gap, 4),
        decision_p_value=dec_p,
        metric="schema_accuracy",
        reference_value=round(ref_schema_acc, 4),
        target_value=round(tgt_schema_acc, 4),
        p_value=min(1.0, 2 * min(schema_p, dec_p)),
        inconclusive=inconclusive,
        fail=fail,
        per_prompt=per_prompt,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    return standard_cli(
        description=__doc__.splitlines()[0],
        test_name=TEST_NAME,
        panel=TOOL_CALLS_PROMPTS,
        run=run_tool_calls,
        runs_dir=RUNS_DIR,
        default_n=DEFAULT_N_SAMPLES,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        default_sleep=DEFAULT_SLEEP_RANGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
