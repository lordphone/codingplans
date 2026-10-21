#!/usr/bin/env python3
"""Executable coding quality — unit-test pass rate on fresh tasks.

The bottom line for a coding plan is whether the code it writes works. This
test asks for small, edge-case-heavy Python functions (coding_tasks.py),
executes each reply against hidden assert-based tests in a sandboxed
subprocess (sandbox.py), and stores pass/fail per sample in the artifact, so
the comparator stays a pure function.

Comparator:
  * pass rate, reference vs target — two-proportion test over all samples
  * paired per-task view: tasks the reference solves reliably (≥2/3 of
    samples) that the target fails reliably (≤1/3) — the "regressions" list
Fails when the pass-rate gap exceeds 10pp and p < 0.05.

Power: 16 tasks × 3 samples = 48 per side detects a ~25pp drop; raise `--n`
to 6–10 for a ~10–15pp detection floor.

Usage:
  python benchmarks/fidelity/coding/test_code_exec.py --endpoint glm5-official
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
_FIDELITY_DIR = _HERE.parent
for _p in (_FIDELITY_DIR, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from coding_tasks import CODE_PANEL_ID, CODE_PROMPTS  # noqa: E402
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
from sandbox import extract_code, run_tests  # noqa: E402
from stats import two_proportion_test  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "code_exec"
DEFAULT_N_SAMPLES = 3
DEFAULT_MAX_TOKENS = 8_000
DEFAULT_SLEEP_RANGE = (2.0, 6.0)
TEMPERATURE = 0.2

ALPHA = 0.05
PASS_GAP_THRESHOLD = 0.10
MIN_SAMPLES_PER_SIDE = 24


def _record(item: PromptItem, resp: ChatResponse) -> dict[str, Any]:
    result = run_tests(extract_code(resp.content), (item.meta or {})["tests"])
    return {
        "passed": result.passed,
        "outcome": result.outcome,
        "detail": result.detail,
        "completion_tokens": resp.completion_tokens,
    }


def run_code_exec(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = CODE_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = None,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    return run_panel(
        endpoint,
        test_name=TEST_NAME,
        panel_id=CODE_PANEL_ID,
        panel=panel,
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range=sleep_range,
        build_request=lambda item, _k: ChatRequest(
            messages=item.messages, temperature=TEMPERATURE, max_tokens=max_tokens
        ),
        record=_record,
        allow_empty=True,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class CodeTaskComparison:
    prompt_idx: int
    name: str
    reference_pass_rate: float
    target_pass_rate: float
    target_failure_kinds: list[str]


@dataclass
class CodeExecReport:
    test_name: str
    reference_label: str
    target_label: str
    reference_samples: int
    target_samples: int
    reference_pass_rate: float
    target_pass_rate: float
    pass_gap_ref_minus_target: float
    regressions: list[str]
    metric: str
    reference_value: float
    target_value: float
    p_value: float
    inconclusive: bool
    fail: bool
    per_task: list[CodeTaskComparison]


def compare_code_exec(reference: RunResult, target: RunResult) -> CodeExecReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)
    by_tgt = {p.prompt_idx: p for p in target.prompts}
    per_task: list[CodeTaskComparison] = []
    regressions: list[str] = []
    r_pass = r_n = t_pass = t_n = 0
    for rp in sorted(reference.prompts, key=lambda p: p.prompt_idx):
        tp = by_tgt.get(rp.prompt_idx)
        if tp is None:
            continue
        rs = [r["passed"] for r in rp.records]
        ts = [r["passed"] for r in tp.records]
        r_pass += sum(rs); r_n += len(rs)
        t_pass += sum(ts); t_n += len(ts)
        r_rate = sum(rs) / len(rs) if rs else 0.0
        t_rate = sum(ts) / len(ts) if ts else 0.0
        if rs and ts and r_rate >= 2 / 3 and t_rate <= 1 / 3:
            regressions.append(rp.name)
        per_task.append(CodeTaskComparison(
            prompt_idx=rp.prompt_idx,
            name=rp.name,
            reference_pass_rate=round(r_rate, 4),
            target_pass_rate=round(t_rate, 4),
            target_failure_kinds=sorted({r["outcome"] for r in tp.records if not r["passed"]}),
        ))

    gap, p = two_proportion_test(r_pass, r_n, t_pass, t_n)
    inconclusive = min(r_n, t_n) < MIN_SAMPLES_PER_SIDE
    r_rate = r_pass / r_n if r_n else 0.0
    t_rate = t_pass / t_n if t_n else 0.0
    return CodeExecReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        reference_samples=r_n,
        target_samples=t_n,
        reference_pass_rate=round(r_rate, 4),
        target_pass_rate=round(t_rate, 4),
        pass_gap_ref_minus_target=round(gap, 4),
        regressions=regressions,
        metric="unit_test_pass_rate",
        reference_value=round(r_rate, 4),
        target_value=round(t_rate, 4),
        p_value=p,
        inconclusive=inconclusive,
        fail=(not inconclusive) and gap > PASS_GAP_THRESHOLD and p < ALPHA,
        per_task=per_task,
    )


def main() -> int:
    return standard_cli(
        description=__doc__.splitlines()[0],
        test_name=TEST_NAME,
        panel=CODE_PROMPTS,
        run=run_code_exec,
        runs_dir=RUNS_DIR,
        default_n=DEFAULT_N_SAMPLES,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        default_sleep=DEFAULT_SLEEP_RANGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
