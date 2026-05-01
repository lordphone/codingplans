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

from common import (  # noqa: E402
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
from needle_common import (  # noqa: E402
    FILLER_CORPUS_VERSION,
    build_multi_needle_messages,
    format_panel_signature,
    generate_filler,
    insert_many_at_depths,
)

RUNS_DIR = _HERE / "runs"

TEST_NAME = "needle_multi"
DEFAULT_N_SAMPLES = 1
DEFAULT_MAX_TOKENS = 200
DEFAULT_SCHEDULE_SEED = 20260425
DEFAULT_SLEEP_RANGE = (1.5, 5.5)
DEFAULT_FILLER_SEED = 271828

# Per-context defaults. K=5 needles is enough to expose middle-depth sag
# (depths 0.1, 0.3, 0.5, 0.7, 0.9) without dragging output token counts
# up far enough to bump max_tokens.
DEFAULT_LENGTHS = (4_000, 8_000, 16_000, 32_000)
DEFAULT_K = 5
DEFAULT_DEPTHS = (0.1, 0.3, 0.5, 0.7, 0.9)

# Fail when target's per-needle recall rate underperforms reference by
# more than this. Multi-needle is sensitive — even a healthy model misses
# a needle now and then — so the threshold is wider than for arithmetic.
FAIL_THRESHOLD_GAP = 0.20


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

    panel_id = (
        f"needle_multi_v1__"
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
    schedule_seed: int = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the multi-needle panel once against `endpoint`."""
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
    # Depth-axis curves averaged over all lengths. The shape (vs the
    # reference's same shape) is the diagnostic — middle-depth sag is
    # the KV-cache signature, flat truncation is the truncation signature.
    reference_depth_recall: dict[str, float]
    target_depth_recall: dict[str, float]
    fail_threshold_gap_gt: float
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


def compare_needle_multi(
    reference: RunResult, target: RunResult
) -> NeedleMultiReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_cell: list[NeedleMultiCellComparison] = []
    # Depth-keyed buckets averaged across cells. We key on the float
    # depth value (formatted) so the report is comparable across runs even
    # if Python's dict ordering changes.
    ref_dep_buckets: dict[str, list[float]] = {}
    tgt_dep_buckets: dict[str, list[float]] = {}
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
            for (_idx, depth, _val), r_rate, t_rate in zip(needles, r_rates, t_rates):
                key = f"{float(depth):g}"
                ref_dep_buckets.setdefault(key, []).append(r_rate)
                tgt_dep_buckets.setdefault(key, []).append(t_rate)

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
            fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
            fail=False,
            per_cell=per_cell,
        )

    ref_overall = ref_total / usable
    tgt_overall = tgt_total / usable

    def _bucket_mean(b: dict[str, list[float]]) -> dict[str, float]:
        return {k: round(sum(v) / len(v), 4) for k, v in b.items() if v}

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
        reference_depth_recall=_bucket_mean(ref_dep_buckets),
        target_depth_recall=_bucket_mean(tgt_dep_buckets),
        fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
        fail=(ref_overall - tgt_overall) > FAIL_THRESHOLD_GAP,
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
    parser.add_argument("--seed", type=int, default=DEFAULT_SCHEDULE_SEED)
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
