#!/usr/bin/env python3
"""Test — Aggregation long-context recall (single-endpoint runner +
comparator).

Scatter M small integers throughout the filler context — each on its own
comment line of a fixed shape — and ask the model for the SUM. Sweep
across context lengths.

Why aggregation is the cleanest of the three needle modes:

  * **Single-needle** asks "is one specific token still there?" — a
    truncation cliff or KV-cache sag both manifest as "miss." The two
    failure modes only separate via the depth axis.
  * **Multi-needle** asks "which depths survived?" — exposes KV-cache
    sag clearly via the smile shape, but the recall metric is fuzzy on
    truncation (you might still get the head needles).
  * **Aggregation** asks for one number, and the magnitude of the
    undercount is monotone in how much context was lost. If the target
    truncated context at character C, every value past C is missed and
    the reported sum drops by exactly that missed mass — the residual
    `(reference_sum − target_sum) / reference_sum` IS the truncation
    fraction. KV-cache degradation produces a similar but more diffuse
    undercount with no sharp cliff in length.

This file follows the standard fidelity test_*.py shape:

  * `run_needle_aggregation(endpoint, …) -> (RunResult, raw_rows)` —
    single endpoint, samples each panel item N times at T=0, parses an
    integer from each completion, returns a self-describing artifact.
  * `compare_needle_aggregation(reference, target) -> AggregationReport` —
    pure function over two `RunResult`s. No HTTP, no env.
  * CLI: run once against one endpoint slug. Compare via `compare.py`.

Usage:
  python benchmarks/fidelity/long_context/test_needle_aggregation.py --endpoint glm5-official
  python benchmarks/fidelity/long_context/test_needle_aggregation.py --endpoint glm5-alibaba
  python benchmarks/fidelity/compare.py runs/<ref>.summary.json runs/<target>.summary.json
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_HERE = Path(__file__).resolve().parent
_FIDELITY_DIR = _HERE.parent
if str(_FIDELITY_DIR) not in sys.path:
    sys.path.insert(0, str(_FIDELITY_DIR))

from framework import (  # noqa: E402
    ChatRequest,
    Endpoint,
    PromptItem,
    PromptOutcome,
    RunResult,
    SCHEMA_VERSION,
    StealthChatClient,
    assert_comparable,
    get_endpoint,
    load_dotenv,
    make_schedule,
    panel_hash,
    utc_stamp,
    write_run_artifacts,
)
from needle import (  # noqa: E402
    FILLER_CORPUS_VERSION,
    build_aggregation_messages,
    format_panel_signature,
    generate_filler,
    insert_many_at_depths,
)

RUNS_DIR = _HERE / "runs"

TEST_NAME = "needle_aggregation"
DEFAULT_N_SAMPLES = 1
DEFAULT_MAX_TOKENS = 30
DEFAULT_SCHEDULE_SEED = 20260425
DEFAULT_SLEEP_RANGE = (1.5, 5.5)
DEFAULT_FILLER_SEED = 161803

DEFAULT_LENGTHS = (4_000, 8_000, 16_000, 32_000)

# Number of values scattered through the filler. Big enough that a small
# truncation produces a noticeable undercount, small enough that K=12
# 2-digit integers comfortably fit in the model's working memory if the
# context is intact.
DEFAULT_M = 12

# Each scattered value is in [10, 99]. Two-digit integers are wide enough
# to make wrong-answer collisions unlikely (a truncated model has to
# coincidentally pick the same wrong sum) and narrow enough that arithmetic
# isn't itself the limiting factor.
_VALUE_LO = 10
_VALUE_HI = 99

# Fail when the relative error of the target's sum exceeds this. Small
# absolute drift (off by ±1 from a single misread) is normal even for
# matched endpoints; > 10% relative error is a real undercount.
FAIL_RELATIVE_ERROR_GT = 0.10


def _make_aggregation_setup(
    *,
    length: int,
    m: int,
    filler_seed: int,
    instance_seed: int,
) -> tuple[list[tuple[float, int]], int]:
    """Choose the M (depth, value) pairs for one panel item.

    Depths are spread uniformly in (0, 1) with a deterministic jitter so
    values don't collide on the same line boundary. Value selection uses
    a separate RNG stream so changing M doesn't shift earlier values."""
    rng = random.Random((filler_seed << 16) ^ instance_seed)
    # Even-spaced anchors with small jitter, kept clear of the very edges
    # so the scatter doesn't degenerate into "all at the start" or "all
    # at the end" — that would defeat the purpose of testing length-loss.
    anchors = [(i + 0.5) / m for i in range(m)]
    depths = [
        max(0.02, min(0.98, a + rng.uniform(-0.4 / m, 0.4 / m)))
        for a in anchors
    ]
    values = [rng.randint(_VALUE_LO, _VALUE_HI) for _ in range(m)]
    pairs = list(zip(depths, values))
    return pairs, sum(values)


def _build_panel(
    *,
    lengths: Sequence[int],
    m: int,
    filler_seed: int,
) -> tuple[list[PromptItem], str]:
    """Build the aggregation panel and return (panel, panel_id).

    Each panel item = one context length. The base filler is generated
    once at the longest length and sliced; per-length value placement is
    re-rolled with a per-length instance seed so different lengths don't
    inherit each other's values verbatim (a model that memorized the L=8k
    sum can't reuse it at L=16k)."""
    base_filler = generate_filler(max(lengths), seed=filler_seed)

    panel: list[PromptItem] = []
    for length in lengths:
        pairs, expected_sum = _make_aggregation_setup(
            length=length, m=m, filler_seed=filler_seed, instance_seed=length
        )
        haystack = base_filler[:length]
        lines = [(f"# COUNT_VALUE = {v}", d) for (d, v) in pairs]
        prompt_filler = insert_many_at_depths(haystack, lines)
        panel.append(PromptItem(
            name=f"L{length}_M{m}",
            messages=build_aggregation_messages(prompt_filler, m=m),
            meta={
                "length_chars": length,
                "m": m,
                "expected_sum": expected_sum,
                # Stored so a comparator could in principle re-bucket by
                # depth (e.g., "did the target miss only the back half?").
                "values": [[d, v] for (d, v) in pairs],
            },
        ))

    panel_id = (
        f"needle_aggregation_v1__"
        f"L{format_panel_signature(list(lengths))}__"
        f"M{m}__"
        f"V{_VALUE_LO}-{_VALUE_HI}__"
        f"s{filler_seed}__"
        f"filler{FILLER_CORPUS_VERSION}"
    )
    return panel, panel_id


# Pull the longest digit run as the model's reported sum. We strip
# thousands separators because polite formatting (e.g. `1,234`) is common.
_INT_RE = re.compile(r"-?\d[\d,]*")


def _parse_sum(content: str) -> int | None:
    """Best-effort integer extraction. Same trick as the arithmetic test:
    longest digit run wins, separators stripped. Tolerant of "the sum is
    347." style replies even though the prompt asks for a bare integer."""
    if not content:
        return None
    matches = _INT_RE.findall(content)
    if not matches:
        return None
    matches.sort(key=lambda s: len(s.replace(",", "").lstrip("-")), reverse=True)
    raw = matches[0].replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None


def run_needle_aggregation(
    endpoint: Endpoint,
    *,
    lengths: Sequence[int] = DEFAULT_LENGTHS,
    m: int = DEFAULT_M,
    filler_seed: int = DEFAULT_FILLER_SEED,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the aggregation panel once against `endpoint`."""
    panel, panel_id = _build_panel(
        lengths=lengths, m=m, filler_seed=filler_seed
    )
    schedule = make_schedule(len(panel), n_samples, seed=schedule_seed)
    outcomes = [
        PromptOutcome(prompt_idx=i, name=item.name, meta=dict(item.meta or {}))
        for i, item in enumerate(panel)
    ]
    raw_rows: list[dict] = []
    total = len(schedule)

    with StealthChatClient(min_sleep_s=sleep_range[0], max_sleep_s=sleep_range[1]) as client:
        for i, call in enumerate(schedule, start=1):
            item = panel[call.prompt_idx]
            req = ChatRequest(
                messages=item.messages,
                temperature=0.0,
                max_tokens=max_tokens,
            )
            try:
                resp = client.chat(endpoint, req)
            except Exception as e:  # noqa: BLE001
                err = {
                    "i": i,
                    "prompt_idx": call.prompt_idx,
                    "prompt_name": item.name,
                    "sample_idx": call.sample_idx,
                    "error": f"{type(e).__name__}: {e}",
                }
                outcomes[call.prompt_idx].errors.append(err)
                raw_rows.append(err)
                if i < total:
                    client.pause()
                continue

            outcomes[call.prompt_idx].completions.append(resp.content)
            parsed = _parse_sum(resp.content)
            expected = int(item.meta["expected_sum"])
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "latency_s": round(resp.latency_s, 4),
                "content": resp.content[:200],
                "parsed_sum": parsed,
                "expected_sum": expected,
                "match": parsed == expected,
            })
            if progress:
                print(
                    f"[{i}/{total}] {item.name:<14} "
                    f"got={parsed} exp={expected} "
                    f"{'OK' if parsed == expected else 'MISS'}",
                    file=sys.stderr,
                    flush=True,
                )
            if i < total:
                client.pause()

    result = RunResult(
        schema_version=SCHEMA_VERSION,
        test_name=TEST_NAME,
        panel_id=panel_id,
        panel_size=len(panel),
        prompt_hash=panel_hash(panel),
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range_s=[float(sleep_range[0]), float(sleep_range[1])],
        stamp_utc=utc_stamp(),
        endpoint_label=endpoint.label,
        endpoint_model=endpoint.model,
        endpoint_base_url=endpoint.base_url.rstrip("/"),
        endpoint_extra_params=dict(endpoint.extra_params),
        user_agent=client.session_user_agent,
        prompts=outcomes,
    )
    return result, raw_rows


# ---------------------------------------------------------------------------
# Comparison (pure function over two RunResults)
# ---------------------------------------------------------------------------


@dataclass
class AggregationCellComparison:
    prompt_idx: int
    name: str
    length_chars: int
    expected_sum: int
    # We summarize each side via its sample mean — the modal would discard
    # information when the sums differ slightly across samples (likely with
    # n_samples > 1). For exact comparisons, n=1 makes mean = single value.
    reference_mean_parsed: float | None
    target_mean_parsed: float | None
    reference_mean_relative_error: float | None
    target_mean_relative_error: float | None


@dataclass
class AggregationReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_cells: int
    n_samples: int
    reference_mean_relative_error: float
    target_mean_relative_error: float
    relative_error_gap_target_minus_ref: float
    # Length-axis curve of mean relative error. Plot this against length:
    # a sharp upward elbow at one length is the truncation signature.
    reference_length_relative_error: dict[int, float]
    target_length_relative_error: dict[int, float]
    fail_threshold_relative_error_gt: float
    fail: bool
    per_cell: list[AggregationCellComparison]


def _mean_parsed(completions: list[str]) -> tuple[float | None, int]:
    """Mean of parsed integer sums across completions. None if zero
    parseable replies; in that case we report None rather than 0 so the
    operator can distinguish "all wrong" from "no parseable output."
    Returns (mean_or_None, n_parsed)."""
    if not completions:
        return None, 0
    parsed = [_parse_sum(c) for c in completions]
    valid = [p for p in parsed if p is not None]
    if not valid:
        return None, 0
    return sum(valid) / len(valid), len(valid)


def _relative_error(parsed_mean: float | None, expected: int) -> float | None:
    """abs(parsed - expected) / expected. None propagates."""
    if parsed_mean is None or expected == 0:
        return None
    return abs(parsed_mean - expected) / expected


def compare_needle_aggregation(
    reference: RunResult, target: RunResult
) -> AggregationReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_cell: list[AggregationCellComparison] = []
    ref_len_buckets: dict[int, list[float]] = {}
    tgt_len_buckets: dict[int, list[float]] = {}
    ref_total = 0.0
    tgt_total = 0.0
    usable = 0

    for idx in sorted(by_idx_ref):
        rp = by_idx_ref[idx]
        tp = by_idx_tgt.get(idx)
        if tp is None:
            continue
        meta = rp.meta or {}
        length = int(meta.get("length_chars", 0))
        expected = int(meta.get("expected_sum", 0))

        r_mean, r_n = _mean_parsed(rp.completions)
        t_mean, t_n = _mean_parsed(tp.completions)
        r_err = _relative_error(r_mean, expected)
        t_err = _relative_error(t_mean, expected)

        per_cell.append(AggregationCellComparison(
            prompt_idx=idx,
            name=rp.name,
            length_chars=length,
            expected_sum=expected,
            reference_mean_parsed=None if r_mean is None else round(r_mean, 4),
            target_mean_parsed=None if t_mean is None else round(t_mean, 4),
            reference_mean_relative_error=None if r_err is None else round(r_err, 4),
            target_mean_relative_error=None if t_err is None else round(t_err, 4),
        ))

        if r_err is not None and t_err is not None:
            usable += 1
            ref_total += r_err
            tgt_total += t_err
            ref_len_buckets.setdefault(length, []).append(r_err)
            tgt_len_buckets.setdefault(length, []).append(t_err)

    if usable == 0:
        return AggregationReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_cells=0,
            n_samples=reference.n_samples,
            reference_mean_relative_error=0.0,
            target_mean_relative_error=0.0,
            relative_error_gap_target_minus_ref=0.0,
            reference_length_relative_error={},
            target_length_relative_error={},
            fail_threshold_relative_error_gt=FAIL_RELATIVE_ERROR_GT,
            fail=False,
            per_cell=per_cell,
        )

    ref_err = ref_total / usable
    tgt_err = tgt_total / usable

    def _bucket_mean(b: dict[int, list[float]]) -> dict[int, float]:
        return {k: round(sum(v) / len(v), 4) for k, v in b.items() if v}

    return AggregationReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_cells=usable,
        n_samples=reference.n_samples,
        reference_mean_relative_error=round(ref_err, 4),
        target_mean_relative_error=round(tgt_err, 4),
        relative_error_gap_target_minus_ref=round(tgt_err - ref_err, 4),
        reference_length_relative_error=_bucket_mean(ref_len_buckets),
        target_length_relative_error=_bucket_mean(tgt_len_buckets),
        fail_threshold_relative_error_gt=FAIL_RELATIVE_ERROR_GT,
        # Fail when the target's mean relative error itself exceeds the
        # threshold AND the gap to reference is meaningful. This avoids a
        # false fail when both endpoints are slightly off in the same way
        # (which would be a model property, not a fidelity gap).
        fail=(tgt_err > FAIL_RELATIVE_ERROR_GT) and (tgt_err - ref_err > FAIL_RELATIVE_ERROR_GT / 2),
        per_cell=per_cell,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_int_list(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", required=True,
                        help="Endpoint slug from targets.ENDPOINTS")
    parser.add_argument("--n", type=int, default=DEFAULT_N_SAMPLES,
                        help=f"Samples per cell (default {DEFAULT_N_SAMPLES})")
    parser.add_argument("--lengths", type=_parse_int_list,
                        default=list(DEFAULT_LENGTHS),
                        help="Comma-separated character lengths to sweep")
    parser.add_argument("--m", type=int, default=DEFAULT_M,
                        help=f"Number of scattered values per prompt "
                             f"(default {DEFAULT_M})")
    parser.add_argument("--filler-seed", type=int, default=DEFAULT_FILLER_SEED)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SCHEDULE_SEED)
    parser.add_argument("--sleep-min", type=float, default=DEFAULT_SLEEP_RANGE[0])
    parser.add_argument("--sleep-max", type=float, default=DEFAULT_SLEEP_RANGE[1])
    args = parser.parse_args()

    load_dotenv()
    endpoint = get_endpoint(args.endpoint)

    n_calls = len(args.lengths) * args.n
    print(
        f"running {TEST_NAME} on {endpoint.label}: "
        f"lengths={args.lengths} M={args.m} n={args.n} "
        f"=> {n_calls} sequential calls",
        file=sys.stderr,
    )

    result, raw_rows = run_needle_aggregation(
        endpoint,
        lengths=args.lengths,
        m=args.m,
        filler_seed=args.filler_seed,
        n_samples=args.n,
        max_tokens=args.max_tokens,
        schedule_seed=args.seed,
        sleep_range=(args.sleep_min, args.sleep_max),
    )
    summary_path, jsonl_path = write_run_artifacts(result, raw_rows, runs_dir=RUNS_DIR)
    print(f"wrote {summary_path}", file=sys.stderr)
    print(f"wrote {jsonl_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
