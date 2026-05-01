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
# Research §6: ask for both count *and* sum to disambiguate truncation
# (count off) from arithmetic error (count right, sum wrong) from
# KV-cache quant (swiss-cheese miss pattern). Index-tagged needles let
# the comparator detect contiguous-tail vs scattered loss patterns.
DEFAULT_N_SAMPLES = 5
DEFAULT_MAX_TOKENS = 30
DEFAULT_SCHEDULE_SEED: int | None = None
DEFAULT_SLEEP_RANGE = (1.5, 5.5)
DEFAULT_FILLER_SEED = 161803

DEFAULT_LENGTHS = (8_000, 16_000, 32_000, 64_000, 128_000)

# Number of values scattered through the filler. Big enough that a small
# truncation produces a noticeable undercount, small enough that 2-digit
# integers comfortably fit in the model's working memory if the context
# is intact.
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
) -> tuple[list[tuple[int, float, int]], int]:
    """Choose M (index, depth, value) triples for one panel item.

    Indices are 1..M assigned in *depth order* — index 1 is the shallowest
    needle, index M the deepest. Research §6: assigning indices in depth
    order is what lets the comparator detect a contiguous tail-loss
    pattern (truncation) vs a swiss-cheese loss pattern (KV-cache quant)
    by inspecting which indices the model returned.

    Depths are even-spaced anchors with small jitter, kept clear of the
    very edges so the scatter doesn't degenerate into "all at the start"
    or "all at the end" — that would defeat the purpose of testing
    length-loss."""
    rng = random.Random((filler_seed << 16) ^ instance_seed)
    anchors = [(i + 0.5) / m for i in range(m)]
    depths = [
        max(0.02, min(0.98, a + rng.uniform(-0.4 / m, 0.4 / m)))
        for a in anchors
    ]
    values = [rng.randint(_VALUE_LO, _VALUE_HI) for _ in range(m)]
    # Indices in depth order: shallower depth -> smaller index.
    indexed = sorted(zip(depths, values))
    triples = [(i + 1, d, v) for i, (d, v) in enumerate(indexed)]
    return triples, sum(values)


def _build_panel(
    *,
    lengths: Sequence[int],
    m: int,
    filler_seed: int,
) -> tuple[list[PromptItem], str]:
    """Build the aggregation panel and return (panel, panel_id).

    Each panel item = one context length. Needles are indexed 1..M in
    depth order, so missing indices reveal whether a model truncated
    (contiguous tail loss) or KV-cache-degraded (scattered loss). The
    base filler is generated once at the longest length and sliced;
    per-length value placement is re-rolled with a per-length instance
    seed so different lengths don't inherit each other's values verbatim
    (a model that memorized the L=8k sum can't reuse it at L=16k)."""
    base_filler = generate_filler(max(lengths), seed=filler_seed)

    panel: list[PromptItem] = []
    for length in lengths:
        triples, expected_sum = _make_aggregation_setup(
            length=length, m=m, filler_seed=filler_seed, instance_seed=length
        )
        haystack = base_filler[:length]
        lines = [(f"# COUNT_VALUE_{i} = {v}", d) for (i, d, v) in triples]
        prompt_filler = insert_many_at_depths(haystack, lines)
        panel.append(PromptItem(
            name=f"L{length}_M{m}",
            messages=build_aggregation_messages(prompt_filler, m=m),
            meta={
                "length_chars": length,
                "m": m,
                "expected_sum": expected_sum,
                "expected_count": m,
                # Stored as (index, depth, value) so the comparator can
                # detect contiguous-tail vs scattered loss patterns.
                "needles": [[i, d, v] for (i, d, v) in triples],
            },
        ))

    # Bumped v1 -> v2: panel content + prompt format both changed.
    panel_id = (
        f"needle_aggregation_v2__"
        f"L{format_panel_signature(list(lengths))}__"
        f"M{m}__"
        f"V{_VALUE_LO}-{_VALUE_HI}__"
        f"s{filler_seed}__"
        f"filler{FILLER_CORPUS_VERSION}"
    )
    return panel, panel_id


# Two-line "count=<int>\nsum=<int>" parser. Tolerant of thousands
# separators, surrounding whitespace, and reordering. If the model only
# emitted one of the two values we still record what we got.
_COUNT_RE = re.compile(r"\bcount\s*[=:]\s*(-?\d[\d,]*)", re.IGNORECASE)
_SUM_RE = re.compile(r"\bsum\s*[=:]\s*(-?\d[\d,]*)", re.IGNORECASE)
# Fallback for models that ignore the format and reply with just the sum.
_BARE_INT_RE = re.compile(r"-?\d[\d,]*")


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return None


def _parse_count_and_sum(content: str) -> tuple[int | None, int | None]:
    """Extract (count, sum) from a free-form completion.

    Looks for `count=<int>` and `sum=<int>` first (the requested format).
    If `sum=` is missing but the response is just a bare integer, treat
    that as the sum and leave count None — a polite-but-noncompliant
    model still gives us the sum signal."""
    if not content:
        return None, None
    count_match = _COUNT_RE.search(content)
    sum_match = _SUM_RE.search(content)
    count = _parse_int(count_match.group(1)) if count_match else None
    summed = _parse_int(sum_match.group(1)) if sum_match else None
    if summed is None:
        # Fallback: the only number in a "347" or "the sum is 347" reply.
        bare = _BARE_INT_RE.findall(content)
        if bare:
            bare.sort(key=lambda s: len(s.replace(",", "").lstrip("-")), reverse=True)
            summed = _parse_int(bare[0])
    return count, summed


def run_needle_aggregation(
    endpoint: Endpoint,
    *,
    lengths: Sequence[int] = DEFAULT_LENGTHS,
    m: int = DEFAULT_M,
    filler_seed: int = DEFAULT_FILLER_SEED,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the aggregation panel once against `endpoint`."""
    if schedule_seed is None:
        import secrets
        schedule_seed = secrets.randbits(31)
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
            parsed_count, parsed_sum = _parse_count_and_sum(resp.content)
            expected_sum = int(item.meta["expected_sum"])
            expected_count = int(item.meta["expected_count"])
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "latency_s": round(resp.latency_s, 4),
                "content": resp.content[:200],
                "parsed_count": parsed_count,
                "parsed_sum": parsed_sum,
                "expected_count": expected_count,
                "expected_sum": expected_sum,
                "count_match": parsed_count == expected_count,
                "sum_match": parsed_sum == expected_sum,
            })
            if progress:
                print(
                    f"[{i}/{total}] {item.name:<14} "
                    f"count={parsed_count}/{expected_count} "
                    f"sum={parsed_sum}/{expected_sum} "
                    f"{'OK' if parsed_sum == expected_sum else 'MISS'}",
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
    expected_count: int
    # Both sides' sample-mean parsed sum and count. Mean (rather than
    # mode) preserves information when sums vary across samples.
    reference_mean_sum: float | None
    target_mean_sum: float | None
    reference_mean_count: float | None
    target_mean_count: float | None
    reference_sum_relative_error: float | None
    target_sum_relative_error: float | None
    reference_count_relative_error: float | None
    target_count_relative_error: float | None


@dataclass
class AggregationReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_cells: int
    n_samples: int
    # Sum-axis aggregate. The headline number — a >10% sum undercount
    # that's larger on the target than the reference is the primary fail
    # signal, regardless of which mechanism caused it.
    reference_mean_sum_relative_error: float
    target_mean_sum_relative_error: float
    sum_error_gap_target_minus_ref: float
    # Count-axis aggregate. Research §6 disambiguation: count error
    # primarily indicates recall/truncation (the model didn't see the
    # needles); sum error with right count indicates arithmetic drift.
    reference_mean_count_relative_error: float
    target_mean_count_relative_error: float
    count_error_gap_target_minus_ref: float
    # Length-axis curve of mean sum relative error. Plot this against
    # length: a sharp upward elbow at one length is the truncation
    # signature.
    reference_length_sum_error: dict[int, float]
    target_length_sum_error: dict[int, float]
    # Each side's diagnosis: "truncation" if count error is the dominant
    # mode, "arithmetic_or_kv_quant" if count is right but sum is wrong,
    # "ok" if both are within threshold. Aggregated across cells.
    reference_diagnosis: str
    target_diagnosis: str
    fail_threshold_relative_error_gt: float
    fail: bool
    per_cell: list[AggregationCellComparison]


def _mean_of(values: list[int | None]) -> tuple[float | None, int]:
    """Mean of valid (non-None) values; returns (mean_or_None, n_valid)."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None, 0
    return sum(valid) / len(valid), len(valid)


def _relative_error(parsed_mean: float | None, expected: int) -> float | None:
    """abs(parsed - expected) / expected. None propagates."""
    if parsed_mean is None or expected == 0:
        return None
    return abs(parsed_mean - expected) / expected


def _diagnose(
    sum_err: float, count_err: float, threshold: float = FAIL_RELATIVE_ERROR_GT
) -> str:
    """Map (sum_err, count_err) to a coarse cause-of-error label.

    Research §6: "If count is wrong, it's a recall/truncation issue. If
    count is right but sum is wrong, it's an arithmetic issue." We add a
    third bucket when both look fine."""
    if sum_err <= threshold and count_err <= threshold:
        return "ok"
    if count_err > threshold:
        return "truncation_or_recall_loss"
    return "arithmetic_or_kv_quant"


def compare_needle_aggregation(
    reference: RunResult, target: RunResult
) -> AggregationReport:
    """Compare two aggregation runs using both count and sum.

    Research §6 critical disambiguation: ask for both `count` and `sum`,
    so we can tell:
      - count off  -> truncation / recall loss (the model didn't see the
                       needles)
      - sum off, count right -> arithmetic drift (KV-cache quant or
                                  weight quant in the addition path)
    """
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_cell: list[AggregationCellComparison] = []
    ref_sum_err_total = 0.0
    tgt_sum_err_total = 0.0
    ref_count_err_total = 0.0
    tgt_count_err_total = 0.0
    ref_len_buckets: dict[int, list[float]] = {}
    tgt_len_buckets: dict[int, list[float]] = {}
    usable = 0

    for idx in sorted(by_idx_ref):
        rp = by_idx_ref[idx]
        tp = by_idx_tgt.get(idx)
        if tp is None:
            continue
        meta = rp.meta or {}
        length = int(meta.get("length_chars", 0))
        expected_sum = int(meta.get("expected_sum", 0))
        expected_count = int(meta.get("expected_count", 0))

        r_sums = [_parse_count_and_sum(c)[1] for c in rp.completions]
        t_sums = [_parse_count_and_sum(c)[1] for c in tp.completions]
        r_counts = [_parse_count_and_sum(c)[0] for c in rp.completions]
        t_counts = [_parse_count_and_sum(c)[0] for c in tp.completions]

        r_sum_mean, _ = _mean_of(r_sums)
        t_sum_mean, _ = _mean_of(t_sums)
        r_count_mean, _ = _mean_of(r_counts)
        t_count_mean, _ = _mean_of(t_counts)

        r_sum_err = _relative_error(r_sum_mean, expected_sum)
        t_sum_err = _relative_error(t_sum_mean, expected_sum)
        r_count_err = _relative_error(r_count_mean, expected_count)
        t_count_err = _relative_error(t_count_mean, expected_count)

        per_cell.append(AggregationCellComparison(
            prompt_idx=idx,
            name=rp.name,
            length_chars=length,
            expected_sum=expected_sum,
            expected_count=expected_count,
            reference_mean_sum=None if r_sum_mean is None else round(r_sum_mean, 4),
            target_mean_sum=None if t_sum_mean is None else round(t_sum_mean, 4),
            reference_mean_count=None if r_count_mean is None else round(r_count_mean, 4),
            target_mean_count=None if t_count_mean is None else round(t_count_mean, 4),
            reference_sum_relative_error=None if r_sum_err is None else round(r_sum_err, 4),
            target_sum_relative_error=None if t_sum_err is None else round(t_sum_err, 4),
            reference_count_relative_error=None if r_count_err is None else round(r_count_err, 4),
            target_count_relative_error=None if t_count_err is None else round(t_count_err, 4),
        ))

        if r_sum_err is not None and t_sum_err is not None:
            usable += 1
            ref_sum_err_total += r_sum_err
            tgt_sum_err_total += t_sum_err
            # Treat missing count as "didn't comply" rather than "0% error":
            # default to 1.0 (100% relative error) so it's flagged.
            ref_count_err_total += r_count_err if r_count_err is not None else 1.0
            tgt_count_err_total += t_count_err if t_count_err is not None else 1.0
            ref_len_buckets.setdefault(length, []).append(r_sum_err)
            tgt_len_buckets.setdefault(length, []).append(t_sum_err)

    if usable == 0:
        return AggregationReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_cells=0,
            n_samples=reference.n_samples,
            reference_mean_sum_relative_error=0.0,
            target_mean_sum_relative_error=0.0,
            sum_error_gap_target_minus_ref=0.0,
            reference_mean_count_relative_error=0.0,
            target_mean_count_relative_error=0.0,
            count_error_gap_target_minus_ref=0.0,
            reference_length_sum_error={},
            target_length_sum_error={},
            reference_diagnosis="no_data",
            target_diagnosis="no_data",
            fail_threshold_relative_error_gt=FAIL_RELATIVE_ERROR_GT,
            fail=False,
            per_cell=per_cell,
        )

    ref_sum_err = ref_sum_err_total / usable
    tgt_sum_err = tgt_sum_err_total / usable
    ref_count_err = ref_count_err_total / usable
    tgt_count_err = tgt_count_err_total / usable

    def _bucket_mean(b: dict[int, list[float]]) -> dict[int, float]:
        return {k: round(sum(v) / len(v), 4) for k, v in b.items() if v}

    return AggregationReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_cells=usable,
        n_samples=reference.n_samples,
        reference_mean_sum_relative_error=round(ref_sum_err, 4),
        target_mean_sum_relative_error=round(tgt_sum_err, 4),
        sum_error_gap_target_minus_ref=round(tgt_sum_err - ref_sum_err, 4),
        reference_mean_count_relative_error=round(ref_count_err, 4),
        target_mean_count_relative_error=round(tgt_count_err, 4),
        count_error_gap_target_minus_ref=round(tgt_count_err - ref_count_err, 4),
        reference_length_sum_error=_bucket_mean(ref_len_buckets),
        target_length_sum_error=_bucket_mean(tgt_len_buckets),
        reference_diagnosis=_diagnose(ref_sum_err, ref_count_err),
        target_diagnosis=_diagnose(tgt_sum_err, tgt_count_err),
        fail_threshold_relative_error_gt=FAIL_RELATIVE_ERROR_GT,
        # Fail when target sum-error itself crosses the threshold AND the
        # gap to reference is meaningful (avoids false-fails when both
        # endpoints are equally bad — a model property, not a fidelity gap).
        fail=(tgt_sum_err > FAIL_RELATIVE_ERROR_GT)
            and (tgt_sum_err - ref_sum_err > FAIL_RELATIVE_ERROR_GT / 2),
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
    parser.add_argument("--seed", type=int, default=DEFAULT_SCHEDULE_SEED,
                        help="Schedule shuffle seed (default: random per run)")
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
