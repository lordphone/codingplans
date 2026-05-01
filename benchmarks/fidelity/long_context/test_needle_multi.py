#!/usr/bin/env python3
"""Test — Multi-needle long-context recall (single-endpoint runner +
comparator).

Plant K unique facts simultaneously at K different depths inside the same
filler context. Ask the model for ALL of them. Sweep across context
lengths.

Why multi-needle adds something single-needle can't:

  * **Single-needle** measures "given this depth, can the model find one
    thing?" — but the model knows there's exactly one needle and can spend
    its whole reasoning budget on the one fact.
  * **Multi-needle** measures "given everything in the context, which
    depths does the model still have access to?" — and the failure
    pattern is more diagnostic than the score:
      - **KV cache quantization** preferentially drops middle-depth values
        while keeping the very first and very last needles sharp. That
        smile-shape (high-low-high recall vs depth) is the cleanest
        signature for KV-cache audits.
      - **Context truncation** drops every needle past the cutoff at once,
        with no smile shape — a flat zero-recall above the cutoff length.

This file follows the standard fidelity test_*.py shape:

  * `run_needle_multi(endpoint, …) -> (RunResult, raw_rows)` — single
    endpoint, samples each panel item N times at T=0, parses K (idx,value)
    pairs from each completion, returns a self-describing artifact.
  * `compare_needle_multi(reference, target) -> NeedleMultiReport` — pure
    function over two `RunResult`s. No HTTP, no env.
  * CLI: run once against one endpoint slug. Compare via `compare.py`.

Usage:
  python benchmarks/fidelity/long_context/test_needle_multi.py --endpoint glm5-official
  python benchmarks/fidelity/long_context/test_needle_multi.py --endpoint glm5-alibaba
  python benchmarks/fidelity/compare.py runs/<ref>.summary.json runs/<target>.summary.json
"""

from __future__ import annotations

import argparse
import random
import re
import string
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
    fit_quadratic,
    get_endpoint,
    load_dotenv,
    make_schedule,
    panel_hash,
    utc_stamp,
    write_run_artifacts,
)
from needle import (  # noqa: E402
    FILLER_CORPUS_VERSION,
    build_multi_needle_messages,
    format_panel_signature,
    generate_filler,
    insert_many_at_depths,
)

RUNS_DIR = _HERE / "runs"

TEST_NAME = "needle_multi"
# Research §5: "K=8–10 is the sweet spot — large enough to fit a quadratic
# curve (test for negative quadratic coefficient = smile) and not so large
# that the needles themselves saturate the context." We pick K=8 with
# spread depths and 5 samples per cell.
DEFAULT_N_SAMPLES = 5
DEFAULT_MAX_TOKENS = 320
DEFAULT_SCHEDULE_SEED: int | None = None
DEFAULT_SLEEP_RANGE = (1.5, 5.5)
DEFAULT_FILLER_SEED = 271828

# Length sweep covers 8K–128K characters (~2.3K–37K tokens) so we span
# typical truncation regimes. K is set by len(DEFAULT_DEPTHS).
DEFAULT_LENGTHS = (8_000, 16_000, 32_000, 64_000, 128_000)
# 8 evenly spread depths anchored away from the very edges (so the model
# can't trivially win via attention-sink primacy/recency).
DEFAULT_DEPTHS = (0.06, 0.20, 0.34, 0.48, 0.62, 0.76, 0.88, 0.95)

# Two failure conditions are checked, either of which fires:
#   (a) overall per-needle recall gap > FAIL_THRESHOLD_GAP, OR
#   (b) target's smile-curvature coefficient is *more positive* than the
#       reference's by more than CURVATURE_GAP_THRESHOLD.
#
# Sign convention: we fit y = a + b*d + c*d² to per-depth recall in [0,1]
# over depth in [0,1]. A smile shape — high recall at d=0 and d=1, low at
# d=0.5 — is a parabola opening upward, i.e. c > 0. KV-cache quantization
# deepens the smile relative to the BF16 baseline, so target_c > ref_c
# means a stronger smile on the target side (research §5).
FAIL_THRESHOLD_GAP = 0.20
CURVATURE_GAP_THRESHOLD = 0.50  # in recall-units / depth² (recall ∈ [0,1])
# Lengths where the reference's overall recall is below this are excluded
# from the depth-curve aggregation, so we only fit smile shapes on
# contexts where the model is actually demonstrating recall.
HEALTHY_LENGTH_RECALL_FLOOR = 0.5


def _needle_value(rng: random.Random) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "-".join(
        "".join(rng.choice(alphabet) for _ in range(5))
        for _ in range(2)
    )


def _build_panel(
    *,
    lengths: Sequence[int],
    depths: Sequence[float],
    filler_seed: int,
) -> tuple[list[PromptItem], str]:
    """Build the multi-needle panel and return (panel, panel_id).

    Each panel item = one context length. Inside that context, we plant
    K=len(depths) needles at the depths listed, each with a deterministic
    unique value. The base filler is generated once at the longest length
    and sliced for each cell, so shorter cells share a strict prefix of
    the same haystack.
    """
    needle_rng = random.Random(filler_seed ^ 0xC3C3C3C3)
    base_filler = generate_filler(max(lengths), seed=filler_seed)
    k = len(depths)

    panel: list[PromptItem] = []
    for length in lengths:
        haystack = base_filler[:length]
        # Pre-roll all needle values for this prompt up front, in order
        # 1..K, before any insertion. Determinism: same panel inputs →
        # same (idx, depth, value) tuples for every run.
        values = [_needle_value(needle_rng) for _ in range(k)]
        needles = [
            (i + 1, d, v) for i, (d, v) in enumerate(zip(depths, values))
        ]
        lines = [
            (f"# UNLOCK_CODE_{i} = {v}", d) for (i, d, v) in needles
        ]
        prompt_filler = insert_many_at_depths(haystack, lines)
        panel.append(PromptItem(
            name=f"L{length}_K{k}",
            messages=build_multi_needle_messages(prompt_filler, k=k),
            meta={
                "length_chars": length,
                "k": k,
                # Needles are stored as JSON-friendly nested lists so they
                # round-trip cleanly through summary.json.
                "needles": [[i, d, v] for (i, d, v) in needles],
            },
        ))

    # Bumped v1 -> v2: panel content changed (K=8 default, depth grid
    # reshuffled). Old artifacts no longer comparable.
    panel_id = (
        f"needle_multi_v2__"
        f"L{format_panel_signature(list(lengths))}__"
        f"D{format_panel_signature(list(depths))}__"
        f"K{k}__"
        f"s{filler_seed}__"
        f"filler{FILLER_CORPUS_VERSION}"
    )
    return panel, panel_id


# Parser for replies of the form `1=QFXR7-MTPL3` (one per line). Tolerant
# of extra whitespace, but anchored to the value shape so prose can't
# poison the parse.
_FACT_RE = re.compile(r"\b(\d+)\s*=\s*([A-Z0-9]{5}-[A-Z0-9]{5})", re.IGNORECASE)


def _parse_facts(content: str) -> dict[int, str]:
    """Extract (idx, value) pairs from a free-form completion. If the
    model emits the same idx twice, the LAST occurrence wins — that
    matches a model walking the context and overwriting an earlier guess."""
    if not content:
        return {}
    out: dict[int, str] = {}
    for m in _FACT_RE.finditer(content):
        idx = int(m.group(1))
        val = m.group(2).upper()
        out[idx] = val
    return out


def run_needle_multi(
    endpoint: Endpoint,
    *,
    lengths: Sequence[int] = DEFAULT_LENGTHS,
    depths: Sequence[float] = DEFAULT_DEPTHS,
    filler_seed: int = DEFAULT_FILLER_SEED,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the multi-needle panel once against `endpoint`."""
    if schedule_seed is None:
        import secrets
        schedule_seed = secrets.randbits(31)
    panel, panel_id = _build_panel(
        lengths=lengths, depths=depths, filler_seed=filler_seed
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
            parsed = _parse_facts(resp.content)
            expected = {int(idx): str(v) for (idx, _d, v) in item.meta["needles"]}
            hits = sum(1 for k, v in expected.items() if parsed.get(k) == v)
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "latency_s": round(resp.latency_s, 4),
                "content": resp.content[:400],
                "parsed": parsed,
                "expected": expected,
                "hits": hits,
                "k": len(expected),
            })
            if progress:
                print(
                    f"[{i}/{total}] {item.name:<14} "
                    f"hits={hits}/{len(expected)}",
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
class NeedleMultiCellComparison:
    prompt_idx: int
    name: str
    length_chars: int
    k: int
    # Per-depth recall fractions: list of fractions ordered by the panel's
    # depth order (e.g. [d0_recall, d1_recall, ..., dK-1_recall]).
    reference_per_depth_recall: list[float]
    target_per_depth_recall: list[float]
    reference_overall_recall: float
    target_overall_recall: float


@dataclass
class NeedleMultiReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_cells: int
    n_samples: int
    reference_overall_recall: float
    target_overall_recall: float
    recall_gap_ref_minus_target: float
    # Depth-axis curves averaged over the *healthy* lengths only (lengths
    # where the reference's overall recall ≥ HEALTHY_LENGTH_RECALL_FLOOR).
    # Mixing in lengths the model is truncating both sides on would smear
    # zero-recall noise into the smile fit.
    reference_depth_recall: dict[str, float]
    target_depth_recall: dict[str, float]
    healthy_lengths: list[int]
    # Quadratic-fit curvature coefficient on per-depth recall. A positive
    # `c` is a smile (recall high at d=0 and d=1, low at d=0.5) — the
    # KV-cache quantization signature (research §5). Compare curvatures
    # between sides; target − reference > 0 means the target has a
    # deeper smile than the reference, i.e. KV-cache degradation.
    reference_curvature: float | None
    target_curvature: float | None
    curvature_gap_target_minus_ref: float | None
    fail_threshold_gap_gt: float
    curvature_gap_threshold: float
    fail: bool
    per_cell: list[NeedleMultiCellComparison]


def _per_depth_recall(
    completions: list[str],
    needles: list[list],  # [[idx, depth, value], ...]
) -> list[float]:
    """Recall rate per needle index, in panel order. If there are no
    completions, returns a list of zeros. Each rate is hits / n_completions."""
    if not completions:
        return [0.0] * len(needles)
    n = len(completions)
    rates: list[float] = []
    for idx_, _depth, value in needles:
        idx = int(idx_)
        hits = 0
        for c in completions:
            parsed = _parse_facts(c)
            if parsed.get(idx) == str(value):
                hits += 1
        rates.append(hits / n)
    return rates


def _curvature(depths: list[float], recalls: list[float]) -> float | None:
    """Quadratic-fit curvature coefficient on per-depth recall.

    Returns None if the fit is degenerate (fewer than 3 distinct depths).
    Sign convention: y = a + b*d + c*d² with d, y ∈ [0,1]. A positive
    coefficient = smile shape (high at edges, low in middle): the
    KV-cache quantization signature."""
    if len(depths) < 3 or len(set(depths)) < 3:
        return None
    try:
        _a, _b, c = fit_quadratic(depths, recalls)
    except ValueError:
        return None
    return c


def compare_needle_multi(
    reference: RunResult, target: RunResult
) -> NeedleMultiReport:
    """Compare two multi-needle runs.

    Two failure modes are flagged:
      1. Overall per-needle recall gap > FAIL_THRESHOLD_GAP — generic
         "target is worse" signal, also catches truncation.
      2. Target's smile-curvature is more negative than reference's by
         more than CURVATURE_GAP_THRESHOLD — research §5 KV-cache
         signature: middle-depth sag worse than the BF16 baseline's
         intrinsic lost-in-the-middle.

    The depth-curve fits are computed over *healthy lengths* only
    (lengths where the reference's overall recall meets a floor) so
    truncation events don't pull zero-recall noise into the smile fit.
    """
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_cell: list[NeedleMultiCellComparison] = []
    # First pass: per-cell rates and identify "healthy" lengths.
    cell_records: list[tuple[int, list[float], list[float], list[float], list[str]]] = []
    # length -> ref overall recall (used to gate healthy lengths)
    ref_overall_by_length: dict[int, float] = {}
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
        needles = list(meta.get("needles") or [])
        if not needles:
            continue
        k = len(needles)

        r_rates = _per_depth_recall(rp.completions, needles)
        t_rates = _per_depth_recall(tp.completions, needles)
        r_overall = sum(r_rates) / k if k else 0.0
        t_overall = sum(t_rates) / k if k else 0.0
        depths = [float(d) for (_, d, _v) in needles]
        keys = [f"{d:g}" for d in depths]

        per_cell.append(NeedleMultiCellComparison(
            prompt_idx=idx,
            name=rp.name,
            length_chars=length,
            k=k,
            reference_per_depth_recall=[round(x, 4) for x in r_rates],
            target_per_depth_recall=[round(x, 4) for x in t_rates],
            reference_overall_recall=round(r_overall, 4),
            target_overall_recall=round(t_overall, 4),
        ))

        if rp.completions and tp.completions:
            usable += 1
            ref_total += r_overall
            tgt_total += t_overall
            cell_records.append((length, depths, r_rates, t_rates, keys))
            ref_overall_by_length[length] = max(
                ref_overall_by_length.get(length, 0.0), r_overall
            )

    if usable == 0:
        return NeedleMultiReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_cells=0,
            n_samples=reference.n_samples,
            reference_overall_recall=0.0,
            target_overall_recall=0.0,
            recall_gap_ref_minus_target=0.0,
            reference_depth_recall={},
            target_depth_recall={},
            healthy_lengths=[],
            reference_curvature=None,
            target_curvature=None,
            curvature_gap_target_minus_ref=None,
            fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
            curvature_gap_threshold=CURVATURE_GAP_THRESHOLD,
            fail=False,
            per_cell=per_cell,
        )

    healthy_lengths = sorted(
        L for L, r in ref_overall_by_length.items()
        if r >= HEALTHY_LENGTH_RECALL_FLOOR
    )

    # Aggregate per-depth recall over healthy lengths only.
    ref_dep_points: list[tuple[float, float]] = []
    tgt_dep_points: list[tuple[float, float]] = []
    for length, depths, r_rates, t_rates, _keys in cell_records:
        if length not in healthy_lengths:
            continue
        for d, rr, tr in zip(depths, r_rates, t_rates):
            ref_dep_points.append((d, rr))
            tgt_dep_points.append((d, tr))

    def _bucket_mean_by_depth(
        points: list[tuple[float, float]],
    ) -> dict[str, float]:
        buckets: dict[str, list[float]] = {}
        for d, v in points:
            buckets.setdefault(f"{d:g}", []).append(v)
        return {k: round(sum(v) / len(v), 4) for k, v in buckets.items() if v}

    ref_depth_recall = _bucket_mean_by_depth(ref_dep_points)
    tgt_depth_recall = _bucket_mean_by_depth(tgt_dep_points)

    # Curvature fit on the depth curve. Use the bucket means (one
    # observation per depth) so equally-weighted points are fit, not
    # ones biased toward depths that appear more often.
    ref_xs = [float(k) for k in ref_depth_recall.keys()]
    ref_ys = [ref_depth_recall[k] for k in ref_depth_recall.keys()]
    tgt_ys = [tgt_depth_recall[k] for k in ref_depth_recall.keys()]
    ref_c = _curvature(ref_xs, ref_ys)
    tgt_c = _curvature(ref_xs, tgt_ys)
    curvature_gap = (
        None if (ref_c is None or tgt_c is None) else round(tgt_c - ref_c, 4)
    )

    ref_overall = ref_total / usable
    tgt_overall = tgt_total / usable
    recall_fail = (ref_overall - tgt_overall) > FAIL_THRESHOLD_GAP
    # Smile = positive c; KV-cache deepens smile, so tgt_c > ref_c.
    curvature_fail = (
        curvature_gap is not None and curvature_gap > CURVATURE_GAP_THRESHOLD
    )

    return NeedleMultiReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_cells=usable,
        n_samples=reference.n_samples,
        reference_overall_recall=round(ref_overall, 4),
        target_overall_recall=round(tgt_overall, 4),
        recall_gap_ref_minus_target=round(ref_overall - tgt_overall, 4),
        reference_depth_recall=ref_depth_recall,
        target_depth_recall=tgt_depth_recall,
        healthy_lengths=healthy_lengths,
        reference_curvature=None if ref_c is None else round(ref_c, 4),
        target_curvature=None if tgt_c is None else round(tgt_c, 4),
        curvature_gap_target_minus_ref=curvature_gap,
        fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
        curvature_gap_threshold=CURVATURE_GAP_THRESHOLD,
        fail=bool(recall_fail or curvature_fail),
        per_cell=per_cell,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_int_list(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x.strip()]


def _parse_float_list(text: str) -> list[float]:
    return [float(x) for x in text.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", required=True,
                        help="Endpoint slug from targets.ENDPOINTS")
    parser.add_argument("--n", type=int, default=DEFAULT_N_SAMPLES,
                        help=f"Samples per cell (default {DEFAULT_N_SAMPLES})")
    parser.add_argument("--lengths", type=_parse_int_list,
                        default=list(DEFAULT_LENGTHS),
                        help="Comma-separated character lengths to sweep")
    parser.add_argument("--depths", type=_parse_float_list,
                        default=list(DEFAULT_DEPTHS),
                        help="Comma-separated fractional depths in [0,1]; "
                             "K is set to len(depths)")
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
        f"lengths={args.lengths} depths={args.depths} (K={len(args.depths)}) "
        f"n={args.n} => {n_calls} sequential calls",
        file=sys.stderr,
    )

    result, raw_rows = run_needle_multi(
        endpoint,
        lengths=args.lengths,
        depths=args.depths,
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
