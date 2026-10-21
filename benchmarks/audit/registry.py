"""Which fidelity tests exist, how to run them, and how to read their reports.

The orchestrator (`run_audit.py`) runs each test through its own CLI in a
subprocess — exactly the command a human would type — so the orchestrator
never re-implements a test and every artifact it produces is identical to a
hand-run one. This module only knows the CLI paths, the per-tier sample
counts, and how to pull a uniform headline out of each comparator's report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

FIDELITY_DIR = Path(__file__).resolve().parent.parent / "fidelity"

__all__ = ["FIDELITY_DIR", "TESTS", "TIERS", "Headline", "TestSpec", "headline"]


@dataclass(frozen=True)
class TestSpec:
    name: str
    family: str
    script: Path
    # Needs `thinking=False` to be meaningful (answer-only T=0 panels).
    # Skipped for models whose thinking cannot be disabled.
    needs_thinking_off: bool = False
    # Extra CLI args per tier (usually a smaller --n for the quick tier).
    tier_args: dict[str, list[str]] = field(default_factory=dict)

    @property
    def runs_dir(self) -> Path:
        from framework import resolve_runs_dir

        return resolve_runs_dir(self.script.parent / "runs")


def _spec(name: str, family: str, script: str, **kw: Any) -> TestSpec:
    return TestSpec(name=name, family=family, script=FIDELITY_DIR / family / script, **kw)


TESTS: dict[str, TestSpec] = {
    t.name: t
    for t in (
        # Serving-stack / protocol checks: cheap, highest real-world yield.
        _spec("token_accounting", "integrity", "test_token_accounting.py"),
        _spec("param_compliance", "integrity", "test_param_compliance.py"),
        _spec("response_cache", "integrity", "test_response_cache.py"),
        _spec("tool_calls", "agentic", "test_tool_calls.py"),
        # Quality under realistic use.
        _spec("code_exec", "coding", "test_code_exec.py"),
        _spec("reasoning_budget", "reasoning", "test_reasoning_budget.py"),
        # Weight-level signals.
        _spec("arithmetic", "model_identity", "test_arithmetic.py", needs_thinking_off=True,
              tier_args={"standard": ["--n", "10"]}),
        _spec("rollout_prefix", "model_identity", "test_rollout_prefix.py", needs_thinking_off=True),
        _spec("entropy", "model_identity", "test_entropy.py", needs_thinking_off=True),
        # Long context.
        _spec("needle_single", "long_context", "test_needle_single.py", needs_thinking_off=True),
        _spec("needle_multi", "long_context", "test_needle_multi.py", needs_thinking_off=True),
        _spec("needle_aggregation", "long_context", "test_needle_aggregation.py", needs_thinking_off=True),
    )
}

# Tiers are cumulative. Rough call counts per endpoint (defaults):
#   quick    ≈ 27 + 80 + 48 + 150            ≈ 300 calls
#   standard ≈ quick + 48 + 48 + 1000        ≈ 1,400 calls
#   full     ≈ standard + 200 + 2000 + 375   ≈ 4,000 calls
TIERS: dict[str, list[str]] = {
    "quick": ["token_accounting", "param_compliance", "response_cache", "tool_calls"],
    "standard": [
        "token_accounting", "param_compliance", "response_cache", "tool_calls",
        "code_exec", "reasoning_budget", "arithmetic",
    ],
    "full": list(TESTS),
}


@dataclass
class Headline:
    metric: str
    reference_value: float | None
    target_value: float | None
    p_value: float | None
    inconclusive: bool
    fail: bool
    summary: str


def _legacy(metric: str, ref_key: str | float, tgt_key: str, usable_key: str,
            fmt: Callable[[dict], str]) -> Callable[[dict], Headline]:
    def read(r: dict) -> Headline:
        ref = r[ref_key] if isinstance(ref_key, str) else ref_key
        return Headline(
            metric=metric,
            reference_value=ref,
            target_value=r[tgt_key],
            p_value=None,
            inconclusive=not r.get(usable_key),
            fail=bool(r["fail"]),
            summary=fmt(r),
        )
    return read


_LEGACY: dict[str, Callable[[dict], Headline]] = {
    "arithmetic": _legacy(
        "digit_accuracy", "reference_digit_accuracy", "target_digit_accuracy", "usable_prompts",
        lambda r: f"Per-digit multiplication accuracy {r['target_digit_accuracy']:.1%} vs "
                  f"{r['reference_digit_accuracy']:.1%} official (gap {r['digit_accuracy_gap_ref_minus_target']:+.1%}).",
    ),
    "rollout_prefix": _legacy(
        "inter_over_intra_prefix_ratio", 1.0, "inter_over_intra_floor_ratio", "usable_prompts",
        lambda r: f"Cross-endpoint common prefix is {r['inter_over_intra_floor_ratio']:.2f}× the "
                  f"same-endpoint floor (1.0 = indistinguishable).",
    ),
    "entropy": _legacy(
        "renyi2_entropy_ratio", 1.0, "mean_renyi2_ratio", "usable_prompts",
        lambda r: f"First-word collision entropy ratio {r['mean_renyi2_ratio']:.2f} (target/official).",
    ),
    "needle_single": _legacy(
        "needle_recall", "reference_overall_accuracy", "target_overall_accuracy", "usable_cells",
        lambda r: f"Needle recall {r['target_overall_accuracy']:.1%} vs {r['reference_overall_accuracy']:.1%}; "
                  f"length-cliff gap {r['cliff_drop_gap_target_minus_ref']:+.2f}.",
    ),
    "needle_multi": _legacy(
        "multi_needle_recall", "reference_overall_recall", "target_overall_recall", "usable_cells",
        lambda r: f"Multi-needle recall {r['target_overall_recall']:.1%} vs {r['reference_overall_recall']:.1%}.",
    ),
    "needle_aggregation": _legacy(
        "sum_relative_error", "reference_mean_sum_relative_error", "target_mean_sum_relative_error",
        "usable_cells",
        lambda r: f"Aggregation sum error {r['target_mean_sum_relative_error']:.1%} vs "
                  f"{r['reference_mean_sum_relative_error']:.1%}; diagnosis {r['target_diagnosis']}.",
    ),
}

_SUMMARIES: dict[str, Callable[[dict], str]] = {
    "tool_calls": lambda r: (
        f"Tool-call schema accuracy {r['target_schema_accuracy']:.1%} vs {r['reference_schema_accuracy']:.1%}; "
        f"trigger similarity {r['trigger_similarity']:.2f}; decision accuracy "
        f"{r['target_decision_accuracy']:.1%} vs {r['reference_decision_accuracy']:.1%}."
    ),
    "token_accounting": lambda r: (
        f"Median prompt-token surplus {r['median_surplus_tokens']:+.0f} tokens (slope {r['slope']:.3f}); "
        f"completion tokens/char ratio {r['completion_ratio_target_over_ref']:.2f}."
        + ("" if r["target_reports_usage"] else " Plan does not report usage.")
    ),
    "param_compliance": lambda r: (
        f"Parameter compliance {r['target_compliance']:.1%} vs {r['reference_compliance']:.1%}; "
        f"temperature sensitivity {r['target_temperature_sensitivity']:.2f} vs "
        f"{r['reference_temperature_sensitivity']:.2f}."
    ),
    "response_cache": lambda r: (
        f"Duplicate replies at T=1: {r['target_duplicate_rate']:.1%} vs {r['reference_duplicate_rate']:.1%}; "
        f"stale nonces: {r['target_stale_nonces']}."
    ),
    "reasoning_budget": lambda r: (
        f"Median reasoning {r['target_median_reasoning']:.0f} vs {r['reference_median_reasoning']:.0f} tokens "
        f"({r['reasoning_ratio_target_over_ref']:.2f}×); accuracy {r['target_accuracy']:.1%} vs "
        f"{r['reference_accuracy']:.1%}."
    ),
    "code_exec": lambda r: (
        f"Unit-test pass rate {r['target_pass_rate']:.1%} vs {r['reference_pass_rate']:.1%}"
        + (f"; regressions: {', '.join(r['regressions'])}." if r["regressions"] else ".")
    ),
}


def headline(test_name: str, report: dict[str, Any]) -> Headline:
    """Uniform view over any comparator's report dict."""
    if test_name in _LEGACY:
        return _LEGACY[test_name](report)
    return Headline(
        metric=report["metric"],
        reference_value=report.get("reference_value"),
        target_value=report.get("target_value"),
        p_value=report.get("p_value"),
        inconclusive=bool(report.get("inconclusive")),
        fail=bool(report["fail"]),
        summary=_SUMMARIES[test_name](report),
    )
