#!/usr/bin/env python3
"""Test 6 — Sampling entropy (single-endpoint runner + comparator).

For each prompt, sample N completions at temperature=1, top_p=1; bucket each
by its normalized first-word token (case-folded, punctuation-stripped — see
`framework.first_word`). Compute Shannon entropy, Renyi-2 collision
entropy, and rank-1 mass per prompt.

Quantization tends to flatten logit distributions, which raises sampling
entropy and lowers rank-1 mass at fixed T. Provider-side logit warping
(secret top-k, repetition penalty) can also *lower* entropy — so the
threshold check is symmetric: fail when |log(ratio)| exceeds the
threshold in either direction.

The primary statistic is **Renyi-2 entropy** (collision entropy):
research §3 notes it is much more sample-efficient than Shannon at
moderate N (a clean Shannon estimate needs ~10k samples per prompt;
Renyi-2 ~1k; rank-1 mass ~200 for a 5% shift). Shannon is reported
alongside for human inspection.

This test is the most fragile of the suite under text-only sampling.
Research §3: "design `test_entropy.py` such that it auto-falls-back to
logprob-based KL divergence when the provider returns logprobs." That
fallback is left as future work and noted in fidelity/THREATS.md.

Usage:
  python benchmarks/fidelity/model_identity/test_entropy.py --endpoint glm5-official --n 200
  python benchmarks/fidelity/model_identity/test_entropy.py --endpoint glm5-alibaba --n 200
  python benchmarks/fidelity/compare.py runs/<ref>.summary.json runs/<target>.summary.json
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
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
    first_word,
    get_endpoint,
    load_dotenv,
    make_schedule,
    panel_hash,
    rank1_mass,
    renyi2_entropy,
    shannon_entropy,
    utc_stamp,
    write_run_artifacts,
)
from prompts import ENTROPY_PANEL_ID, ENTROPY_PROMPTS  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "entropy"
# Research §3: text-only entropy detection is intrinsically weak; the
# expected INT4 effect size is 0.05–0.3 bits. N=200 is the practical
# minimum for a usable Renyi-2 estimate; ~1000 would be ideal.
DEFAULT_N_SAMPLES = 200
DEFAULT_MAX_TOKENS = 5
DEFAULT_SCHEDULE_SEED: int | None = None
DEFAULT_SLEEP_RANGE = (1.0, 4.0)
# Symmetric threshold on the Renyi-2 entropy ratio. Research §3 false
# positives: provider top-k truncation can *lower* entropy (opposite
# direction from quantization). We fail in either direction so a covert
# tail-truncation also gets caught.
FAIL_RATIO_THRESHOLD = 1.15
FAIL_LOG_RATIO_THRESHOLD = math.log2(FAIL_RATIO_THRESHOLD)


def run_entropy(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = ENTROPY_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the entropy panel once against `endpoint`. Returns
    `(RunResult, raw_rows)`."""
    if schedule_seed is None:
        import secrets
        schedule_seed = secrets.randbits(31)
    panel = list(panel)
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
                temperature=1.0,
                max_tokens=max_tokens,
                extra_params={"top_p": 1.0},
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
            fw = first_word(resp.content)
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "latency_s": round(resp.latency_s, 4),
                "content": resp.content[:80],
                "first_word": fw,
            })
            if progress:
                print(
                    f"[{i}/{total}] {item.name:<26} first={fw!r}",
                    file=sys.stderr,
                    flush=True,
                )
            if i < total:
                client.pause()

    result = RunResult(
        schema_version=SCHEMA_VERSION,
        test_name=TEST_NAME,
        panel_id=ENTROPY_PANEL_ID,
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
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class EntropyPromptComparison:
    prompt_idx: int
    name: str
    n_reference: int
    n_target: int
    reference_unique_first_words: int
    target_unique_first_words: int
    reference_shannon_bits: float
    target_shannon_bits: float
    reference_renyi2_bits: float
    target_renyi2_bits: float
    reference_rank1_mass: float
    target_rank1_mass: float
    # Renyi-2 ratio is the primary per-prompt signal. log2-ratio lets us
    # apply a symmetric threshold (entropy can move in either direction).
    renyi2_ratio_target_over_reference: float | None
    abs_log2_renyi2_ratio: float | None
    skipped: bool


@dataclass
class EntropyReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_prompts: int
    n_samples: int
    # Primary statistic: Renyi-2 collision-entropy ratio (target/reference).
    # Reported alongside Shannon for human inspection. Mean rank-1 mass is
    # the fallback signal at small N.
    mean_renyi2_ratio: float
    median_renyi2_ratio: float
    mean_shannon_ratio: float
    mean_reference_rank1_mass: float
    mean_target_rank1_mass: float
    rank1_mass_gap_ref_minus_target: float
    prompts_over_threshold: int
    fraction_over_threshold: float
    ratio_threshold: float
    fail: bool
    per_prompt: list[EntropyPromptComparison]


def compare_entropy(reference: RunResult, target: RunResult) -> EntropyReport:
    """Symmetric Renyi-2 ratio test on first-token distributions.

    Research §3: INT4 quantization typically *raises* sampling entropy
    (flatter logits → ratio > 1); provider top-k / repetition-penalty
    warping typically *lowers* it (ratio < 1). We test |log2(ratio)| so
    either direction triggers a fail."""
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_prompt: list[EntropyPromptComparison] = []
    renyi_ratios: list[float] = []
    shannon_ratios: list[float] = []
    abs_log_ratios: list[float] = []
    ref_rank1: list[float] = []
    tgt_rank1: list[float] = []

    for idx in sorted(by_idx_ref):
        rp = by_idx_ref[idx]
        tp = by_idx_tgt.get(idx)
        if tp is None:
            continue
        r_words = [first_word(c) for c in rp.completions]
        t_words = [first_word(c) for c in tp.completions]
        if not r_words or not t_words:
            per_prompt.append(EntropyPromptComparison(
                prompt_idx=idx,
                name=rp.name,
                n_reference=len(r_words),
                n_target=len(t_words),
                reference_unique_first_words=len(set(r_words)),
                target_unique_first_words=len(set(t_words)),
                reference_shannon_bits=0.0,
                target_shannon_bits=0.0,
                reference_renyi2_bits=0.0,
                target_renyi2_bits=0.0,
                reference_rank1_mass=0.0,
                target_rank1_mass=0.0,
                renyi2_ratio_target_over_reference=None,
                abs_log2_renyi2_ratio=None,
                skipped=True,
            ))
            continue
        h_r_shannon = shannon_entropy(r_words)
        h_t_shannon = shannon_entropy(t_words)
        h_r_renyi = renyi2_entropy(r_words)
        h_t_renyi = renyi2_entropy(t_words)
        r_r1 = rank1_mass(r_words)
        t_r1 = rank1_mass(t_words)
        ref_rank1.append(r_r1)
        tgt_rank1.append(t_r1)
        if h_r_shannon > 0:
            shannon_ratios.append(h_t_shannon / h_r_shannon)
        # Renyi-2 ratio + abs log2 for symmetric threshold. Skip when the
        # reference is itself ~0 (degenerate prompt with one dominant
        # answer); rank-1 mass picks up the slack at the aggregate level.
        renyi_ratio: float | None = None
        abs_log_ratio: float | None = None
        if h_r_renyi > 0 and h_t_renyi > 0:
            renyi_ratio = h_t_renyi / h_r_renyi
            abs_log_ratio = abs(math.log2(renyi_ratio))
            renyi_ratios.append(renyi_ratio)
            abs_log_ratios.append(abs_log_ratio)
        per_prompt.append(EntropyPromptComparison(
            prompt_idx=idx,
            name=rp.name,
            n_reference=len(r_words),
            n_target=len(t_words),
            reference_unique_first_words=len(set(r_words)),
            target_unique_first_words=len(set(t_words)),
            reference_shannon_bits=round(h_r_shannon, 4),
            target_shannon_bits=round(h_t_shannon, 4),
            reference_renyi2_bits=round(h_r_renyi, 4),
            target_renyi2_bits=round(h_t_renyi, 4),
            reference_rank1_mass=round(r_r1, 4),
            target_rank1_mass=round(t_r1, 4),
            renyi2_ratio_target_over_reference=(
                None if renyi_ratio is None else round(renyi_ratio, 4)
            ),
            abs_log2_renyi2_ratio=(
                None if abs_log_ratio is None else round(abs_log_ratio, 4)
            ),
            skipped=False,
        ))

    if not renyi_ratios:
        return EntropyReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_prompts=0,
            n_samples=reference.n_samples,
            mean_renyi2_ratio=0.0,
            median_renyi2_ratio=0.0,
            mean_shannon_ratio=0.0,
            mean_reference_rank1_mass=0.0,
            mean_target_rank1_mass=0.0,
            rank1_mass_gap_ref_minus_target=0.0,
            prompts_over_threshold=0,
            fraction_over_threshold=0.0,
            ratio_threshold=FAIL_RATIO_THRESHOLD,
            fail=False,
            per_prompt=per_prompt,
        )

    over = sum(1 for lr in abs_log_ratios if lr > FAIL_LOG_RATIO_THRESHOLD)
    sorted_ratios = sorted(renyi_ratios)
    median_renyi = sorted_ratios[len(sorted_ratios) // 2]
    ref_r1_mean = mean(ref_rank1) if ref_rank1 else 0.0
    tgt_r1_mean = mean(tgt_rank1) if tgt_rank1 else 0.0
    return EntropyReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_prompts=len(renyi_ratios),
        n_samples=reference.n_samples,
        mean_renyi2_ratio=round(mean(renyi_ratios), 4),
        median_renyi2_ratio=round(median_renyi, 4),
        mean_shannon_ratio=round(mean(shannon_ratios), 4) if shannon_ratios else 0.0,
        mean_reference_rank1_mass=round(ref_r1_mean, 4),
        mean_target_rank1_mass=round(tgt_r1_mean, 4),
        rank1_mass_gap_ref_minus_target=round(ref_r1_mean - tgt_r1_mean, 4),
        prompts_over_threshold=over,
        fraction_over_threshold=round(over / len(abs_log_ratios), 4),
        ratio_threshold=FAIL_RATIO_THRESHOLD,
        fail=(over / len(abs_log_ratios)) > 0.5,
        per_prompt=per_prompt,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", required=True,
                        help="Endpoint slug from targets.ENDPOINTS")
    parser.add_argument("--n", type=int, default=DEFAULT_N_SAMPLES,
                        help=f"Samples per prompt (default {DEFAULT_N_SAMPLES}; "
                             f"~1000 for clean Renyi-2)")
    parser.add_argument("--panel-size", type=int, default=len(ENTROPY_PROMPTS),
                        help="Truncate panel for cheap dry runs")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"max_tokens per request (default {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SCHEDULE_SEED,
                        help="Schedule shuffle seed (default: random per run)")
    parser.add_argument("--sleep-min", type=float, default=DEFAULT_SLEEP_RANGE[0])
    parser.add_argument("--sleep-max", type=float, default=DEFAULT_SLEEP_RANGE[1])
    args = parser.parse_args()

    load_dotenv()
    endpoint = get_endpoint(args.endpoint)
    panel = list(ENTROPY_PROMPTS[: args.panel_size])

    n_calls = len(panel) * args.n
    print(
        f"running {TEST_NAME} on {endpoint.label}: "
        f"panel={len(panel)} n={args.n} max_tokens={args.max_tokens} "
        f"=> {n_calls} sequential calls",
        file=sys.stderr,
    )

    result, raw_rows = run_entropy(
        endpoint,
        panel=panel,
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
