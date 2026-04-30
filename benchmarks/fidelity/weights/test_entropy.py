#!/usr/bin/env python3
"""Test 6 — Sampling entropy (single-endpoint runner + comparator).

For each prompt, sample N completions at temperature=1, top_p=1; bucket each
by its first whitespace-bounded token (a tokenizer-free proxy for the
model's first emitted token); compute Shannon entropy per prompt.

Quantization tends to flatten logit distributions, which raises sampling
entropy at fixed T. Comparison aggregates the per-prompt
target/reference entropy ratio and fails if a majority of prompts exceed
1.15.

Usage:
  python benchmarks/fidelity/weights/test_entropy.py --endpoint glm5-official --n 50
  python benchmarks/fidelity/weights/test_entropy.py --endpoint glm5-alibaba --n 50
  python benchmarks/fidelity/compare.py runs/<ref>.summary.json runs/<target>.summary.json
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
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
    first_word,
    get_endpoint,
    load_dotenv,
    make_schedule,
    panel_hash,
    shannon_entropy,
    utc_stamp,
    write_run_artifacts,
)
from prompts import ENTROPY_PANEL_ID, ENTROPY_PROMPTS  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "entropy"
DEFAULT_N_SAMPLES = 50
DEFAULT_MAX_TOKENS = 5
DEFAULT_SCHEDULE_SEED = 20260425
DEFAULT_SLEEP_RANGE = (1.0, 4.0)
FAIL_RATIO_THRESHOLD = 1.15


def run_entropy(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = ENTROPY_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the entropy panel once against `endpoint`. Returns
    `(RunResult, raw_rows)`."""
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
    reference_first_word_entropy_bits: float
    target_first_word_entropy_bits: float
    entropy_ratio_target_over_reference: float | None
    skipped: bool


@dataclass
class EntropyReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_prompts: int
    n_samples: int
    mean_entropy_ratio: float
    median_entropy_ratio: float
    prompts_over_threshold: int
    fraction_over_threshold: float
    ratio_threshold: float
    fail: bool
    per_prompt: list[EntropyPromptComparison]


def compare_entropy(reference: RunResult, target: RunResult) -> EntropyReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_prompt: list[EntropyPromptComparison] = []
    ratios: list[float] = []

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
                reference_first_word_entropy_bits=0.0,
                target_first_word_entropy_bits=0.0,
                entropy_ratio_target_over_reference=None,
                skipped=True,
            ))
            continue
        h_r = shannon_entropy(r_words)
        h_t = shannon_entropy(t_words)
        ratio = (h_t / h_r) if h_r > 0 else float("inf")
        ratios.append(ratio)
        per_prompt.append(EntropyPromptComparison(
            prompt_idx=idx,
            name=rp.name,
            n_reference=len(r_words),
            n_target=len(t_words),
            reference_unique_first_words=len(set(r_words)),
            target_unique_first_words=len(set(t_words)),
            reference_first_word_entropy_bits=round(h_r, 4),
            target_first_word_entropy_bits=round(h_t, 4),
            entropy_ratio_target_over_reference=round(ratio, 4),
            skipped=False,
        ))

    if not ratios:
        return EntropyReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_prompts=0,
            n_samples=reference.n_samples,
            mean_entropy_ratio=0.0,
            median_entropy_ratio=0.0,
            prompts_over_threshold=0,
            fraction_over_threshold=0.0,
            ratio_threshold=FAIL_RATIO_THRESHOLD,
            fail=False,
            per_prompt=per_prompt,
        )

    over = sum(1 for r in ratios if r > FAIL_RATIO_THRESHOLD)
    return EntropyReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_prompts=len(ratios),
        n_samples=reference.n_samples,
        mean_entropy_ratio=round(mean(ratios), 4),
        median_entropy_ratio=round(sorted(ratios)[len(ratios) // 2], 4),
        prompts_over_threshold=over,
        fraction_over_threshold=round(over / len(ratios), 4),
        ratio_threshold=FAIL_RATIO_THRESHOLD,
        fail=(over / len(ratios)) > 0.5,
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
                        help=f"Samples per prompt (default {DEFAULT_N_SAMPLES}; spec: 200)")
    parser.add_argument("--panel-size", type=int, default=len(ENTROPY_PROMPTS),
                        help="Truncate panel for cheap dry runs")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"max_tokens per request (default {DEFAULT_MAX_TOKENS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SCHEDULE_SEED)
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
