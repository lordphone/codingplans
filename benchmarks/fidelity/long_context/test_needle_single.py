#!/usr/bin/env python3
"""Test — Single-needle long-context recall (single-endpoint runner +
comparator).

Plant exactly one unique fact at a parameterized depth inside a long
Python-shaped filler context. Ask the model to echo the fact back. Sweep
across a 2D grid of (context_length, depth) cells.

The shape of the recall curve across the grid is the primary diagnostic:

  * **Hard cliff above a specific length** → context truncation. The
    target accepted the prompt but only saw a prefix.
  * **Middle-depth sag at otherwise-OK lengths** → KV cache quantization.
    Beginning and end tokens stay sharp; middle-depth needles get blurred
    out by the lossy cache representation.
  * **Uniform recall drop across the whole grid** → either weight
    quantization severe enough to hurt instruction-following, or a model
    swap to something materially weaker. Cross-reference with
    `model_identity/test_arithmetic.py` and `model_identity/test_rollout_prefix.py`.

This file follows the standard fidelity test_*.py shape:

  * `run_single_needle(endpoint, …) -> (RunResult, raw_rows)` — single
    endpoint, samples each grid cell N times at T=0, parses an exact
    match, returns a self-describing artifact.
  * `compare_single_needle(reference, target) -> SingleNeedleReport` —
    pure function over two `RunResult`s. No HTTP, no env.
  * CLI: run once against one endpoint slug. Compare via `compare.py`.

Usage:
  python benchmarks/fidelity/long_context/test_needle_single.py --endpoint glm5-official
  python benchmarks/fidelity/long_context/test_needle_single.py --endpoint glm5-alibaba
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
    get_endpoint,
    load_dotenv,
    make_schedule,
    panel_hash,
    utc_stamp,
    write_run_artifacts,
)
from needle import (  # noqa: E402
    FILLER_CORPUS_VERSION,
    build_single_needle_messages,
    format_panel_signature,
    generate_filler,
    insert_at_depth,
    make_length_depth_grid,
)

RUNS_DIR = _HERE / "runs"

TEST_NAME = "needle_single"
DEFAULT_N_SAMPLES = 1
DEFAULT_MAX_TOKENS = 50
DEFAULT_SCHEDULE_SEED = 20260425
DEFAULT_SLEEP_RANGE = (1.5, 5.5)
DEFAULT_FILLER_SEED = 314159

# Sweep defaults. Lengths are in CHARACTERS, not tokens; the rough rule of
# thumb for English/code is ~3.5 chars per token, so 32k chars ≈ 9k tokens.
# Default grid stays well under common 32k-token context windows.
DEFAULT_LENGTHS = (4_000, 8_000, 16_000, 32_000)
DEFAULT_DEPTHS = (0.05, 0.25, 0.5, 0.75, 0.95)

# Fail when target accuracy underperforms reference by more than this. Set
# wide on purpose — we expect a few stochastic misses on T=0 even for
# matched endpoints. Sharper cell-level signals are surfaced in per_cell.
FAIL_THRESHOLD_GAP = 0.20


def _needle_value(rng: random.Random) -> str:
    """Generate a 2-group alphanumeric token like `QFXR7-MTPL3`. Long enough
    to be distinctive, short enough to fit in a 50-token reply."""
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
    """Build the single-needle panel and return (panel, panel_id).

    Each cell gets a deterministic needle value derived from a panel-level
    PRNG seeded with `filler_seed`. The filler itself is generated once at
    the longest length and sliced for each cell — that keeps every shorter
    cell's haystack a strict prefix of the longer ones, so length effects
    are isolated from "different filler bytes" effects."""
    needle_rng = random.Random(filler_seed ^ 0xA5A5A5A5)  # decorrelate from filler stream
    base_filler = generate_filler(max(lengths), seed=filler_seed)

    panel: list[PromptItem] = []
    for length, depth in make_length_depth_grid(lengths, depths):
        # Fresh random-looking but deterministic value per (length, depth).
        value = _needle_value(needle_rng)
        haystack = base_filler[:length]
        needle_line = f"# UNLOCK_CODE = {value}"
        prompt_text_filler = insert_at_depth(haystack, needle_line, depth)
        panel.append(PromptItem(
            name=f"L{length}_D{depth:g}",
            messages=build_single_needle_messages(prompt_text_filler),
            meta={
                "length_chars": length,
                "depth": depth,
                "expected": value,
            },
        ))

    panel_id = (
        f"needle_single_v1__"
        f"L{format_panel_signature(list(lengths))}__"
        f"D{format_panel_signature(list(depths))}__"
        f"s{filler_seed}__"
        f"filler{FILLER_CORPUS_VERSION}"
    )
    return panel, panel_id


# Used for parsing the model's reply. We expect a bare value like
# `QFXR7-MTPL3` but allow a small amount of slop (quoting, prose) by
# extracting the longest 5-char–dash–5-char token in the response.
_VALUE_RE = re.compile(r"[A-Z0-9]{5}-[A-Z0-9]{5}")


def _parse_value(content: str) -> str | None:
    """Extract the inserted needle value from a free-form completion.

    The instruction asks for "only the value, nothing else", but tolerant
    parsing makes the test resilient to a polite model that wraps its
    answer in quotes or a "the unlock code is …" preamble. We match the
    fixed shape and pick the longest unique match — if the model emits
    multiple, that itself is suspicious and would surface as a `match=False`
    even though parsing succeeded."""
    if not content:
        return None
    m = _VALUE_RE.findall(content.upper())
    if not m:
        return None
    # If the model echoes >1 candidate, pick the first — it's the most
    # likely "answer." All candidates are recorded in the JSONL log via
    # raw `content` so the operator can inspect mismatches.
    return m[0]


def run_single_needle(
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
    """Run the single-needle panel once against `endpoint`."""
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
            except Exception as e:  # noqa: BLE001 — record and keep going
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
            parsed = _parse_value(resp.content)
            expected = item.meta["expected"]
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "latency_s": round(resp.latency_s, 4),
                "content": resp.content[:200],
                "parsed": parsed,
                "expected": expected,
                "match": parsed == expected,
            })
            if progress:
                print(
                    f"[{i}/{total}] {item.name:<22} "
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
class SingleNeedleCellComparison:
    prompt_idx: int
    name: str
    length_chars: int
    depth: float
    reference_match_rate: float
    target_match_rate: float
    n_reference: int
    n_target: int


@dataclass
class SingleNeedleReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_cells: int
    n_samples: int
    reference_overall_accuracy: float
    target_overall_accuracy: float
    accuracy_gap_ref_minus_target: float
    # Length-axis curves: index by length, mean recall across all depths
    # at that length. Used to spot context truncation cliffs.
    reference_length_accuracy: dict[int, float]
    target_length_accuracy: dict[int, float]
    # Depth-axis curves: index by depth, mean recall across all lengths
    # at that depth. Used to spot KV-cache middle-depth sag.
    reference_depth_accuracy: dict[str, float]
    target_depth_accuracy: dict[str, float]
    fail_threshold_gap_gt: float
    fail: bool
    per_cell: list[SingleNeedleCellComparison]


def _match_rate(completions: list[str], expected: str) -> tuple[float, int]:
    """Fraction of completions whose parsed value equals `expected`."""
    if not completions:
        return 0.0, 0
    hits = sum(1 for c in completions if _parse_value(c) == expected)
    return hits / len(completions), len(completions)


def _bucket_mean(by_key: dict[object, list[float]]) -> dict[object, float]:
    return {k: (sum(v) / len(v) if v else 0.0) for k, v in by_key.items()}


def compare_single_needle(
    reference: RunResult, target: RunResult
) -> SingleNeedleReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_cell: list[SingleNeedleCellComparison] = []
    ref_len_buckets: dict[int, list[float]] = {}
    tgt_len_buckets: dict[int, list[float]] = {}
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
        expected = str(meta.get("expected", ""))
        length = int(meta.get("length_chars", 0))
        depth = float(meta.get("depth", 0.0))
        depth_key = f"{depth:g}"

        r_rate, r_n = _match_rate(rp.completions, expected)
        t_rate, t_n = _match_rate(tp.completions, expected)
        per_cell.append(SingleNeedleCellComparison(
            prompt_idx=idx,
            name=rp.name,
            length_chars=length,
            depth=depth,
            reference_match_rate=round(r_rate, 4),
            target_match_rate=round(t_rate, 4),
            n_reference=r_n,
            n_target=t_n,
        ))
        if r_n and t_n:
            usable += 1
            ref_total += r_rate
            tgt_total += t_rate
            ref_len_buckets.setdefault(length, []).append(r_rate)
            tgt_len_buckets.setdefault(length, []).append(t_rate)
            ref_dep_buckets.setdefault(depth_key, []).append(r_rate)
            tgt_dep_buckets.setdefault(depth_key, []).append(t_rate)

    if usable == 0:
        return SingleNeedleReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_cells=0,
            n_samples=reference.n_samples,
            reference_overall_accuracy=0.0,
            target_overall_accuracy=0.0,
            accuracy_gap_ref_minus_target=0.0,
            reference_length_accuracy={},
            target_length_accuracy={},
            reference_depth_accuracy={},
            target_depth_accuracy={},
            fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
            fail=False,
            per_cell=per_cell,
        )

    ref_acc = ref_total / usable
    tgt_acc = tgt_total / usable
    return SingleNeedleReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_cells=usable,
        n_samples=reference.n_samples,
        reference_overall_accuracy=round(ref_acc, 4),
        target_overall_accuracy=round(tgt_acc, 4),
        accuracy_gap_ref_minus_target=round(ref_acc - tgt_acc, 4),
        reference_length_accuracy={k: round(v, 4) for k, v in _bucket_mean(ref_len_buckets).items()},
        target_length_accuracy={k: round(v, 4) for k, v in _bucket_mean(tgt_len_buckets).items()},
        reference_depth_accuracy={k: round(v, 4) for k, v in _bucket_mean(ref_dep_buckets).items()},
        target_depth_accuracy={k: round(v, 4) for k, v in _bucket_mean(tgt_dep_buckets).items()},
        fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
        fail=(ref_acc - tgt_acc) > FAIL_THRESHOLD_GAP,
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
                        help="Comma-separated fractional depths in [0,1]")
    parser.add_argument("--filler-seed", type=int, default=DEFAULT_FILLER_SEED)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"max_tokens per request (default {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SCHEDULE_SEED,
                        help="Schedule shuffle seed")
    parser.add_argument("--sleep-min", type=float, default=DEFAULT_SLEEP_RANGE[0])
    parser.add_argument("--sleep-max", type=float, default=DEFAULT_SLEEP_RANGE[1])
    args = parser.parse_args()

    load_dotenv()
    endpoint = get_endpoint(args.endpoint)

    n_calls = len(args.lengths) * len(args.depths) * args.n
    print(
        f"running {TEST_NAME} on {endpoint.label}: "
        f"lengths={args.lengths} depths={args.depths} n={args.n} "
        f"=> {n_calls} sequential calls",
        file=sys.stderr,
    )

    result, raw_rows = run_single_needle(
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
