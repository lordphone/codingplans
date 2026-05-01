#!/usr/bin/env python3
"""Test 1 — Long deterministic rollout divergence (single-endpoint runner +
comparator).

For each prompt, sample N completions at temperature=0; later compare two
endpoints via:
  * mean pairwise prefix-character agreement *within* each side (intra), and
  * prefix-character agreement *between* the two sides' modal completions
    (inter).

If the two endpoints serve the same weights, batch nondeterminism is the
only thing that can cause divergence, so inter ≈ intra. Quantization breaks
ties at narrow-margin token positions, snowballing into earlier divergence.
The comparator fails when `inter / intra_floor < 0.5`.

Usage:
  python benchmarks/fidelity/model_identity/test_rollout_prefix.py --endpoint glm5-official --n 10 --max-tokens 2000
  python benchmarks/fidelity/model_identity/test_rollout_prefix.py --endpoint glm5-alibaba --n 10 --max-tokens 2000
  python benchmarks/fidelity/compare.py runs/<ref>.summary.json runs/<target>.summary.json

Outputs land under benchmarks/fidelity/model_identity/runs/.
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

from framework import (  # noqa: E402
    ChatRequest,
    Endpoint,
    PromptItem,
    PromptOutcome,
    RunResult,
    SCHEMA_VERSION,
    StealthChatClient,
    assert_comparable,
    common_prefix_chars,
    get_endpoint,
    load_dotenv,
    make_schedule,
    mean_pairwise_prefix,
    modal,
    normalize_text,
    panel_hash,
    utc_stamp,
    write_run_artifacts,
)
from prompts import ROLLOUT_PANEL_ID, ROLLOUT_PROMPTS  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "rollout_prefix"
DEFAULT_N_SAMPLES = 10
DEFAULT_MAX_TOKENS = 2000
DEFAULT_SCHEDULE_SEED: int | None = None
DEFAULT_SLEEP_RANGE = (1.5, 5.5)
FAIL_RATIO_THRESHOLD = 0.5


def _intra_pairwise_prefix(samples: list[str]) -> float:
    """Mean pairwise common-prefix length within one side's samples.

    With T=0 batch nondeterminism, this is the per-prompt 'noise floor'
    that the inter-side cross-pair statistic gets compared against."""
    if len(samples) < 2:
        return float(len(samples[0])) if samples else 0.0
    total = 0
    pairs = 0
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            total += common_prefix_chars(samples[i], samples[j])
            pairs += 1
    return total / pairs


def run_rollout_prefix(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = ROLLOUT_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the rollout panel once against `endpoint`. Returns
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
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "content_len": len(resp.content),
                "finish_reason": resp.finish_reason,
                "latency_s": round(resp.latency_s, 4),
                "content_head": resp.content[:200],
            })
            if progress:
                print(
                    f"[{i}/{total}] {item.name:<26} "
                    f"len={len(resp.content):5d} t={resp.latency_s:6.2f}s",
                    file=sys.stderr,
                    flush=True,
                )
            if i < total:
                client.pause()

    result = RunResult(
        schema_version=SCHEMA_VERSION,
        test_name=TEST_NAME,
        panel_id=ROLLOUT_PANEL_ID,
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
class RolloutPromptComparison:
    prompt_idx: int
    name: str
    n_reference: int
    n_target: int
    reference_intra_prefix_mean: float
    target_intra_prefix_mean: float
    # Mean common-prefix length across all (ref, tgt) cross-pairs. Replaces
    # the old modal-vs-modal singleton statistic, which collapsed under T=0
    # batch noise to "common_prefix(r[0], t[0])" — random, not signal.
    inter_pairwise_prefix_mean: float
    # Modal-vs-modal kept as a forensic side report.
    inter_modal_prefix_chars: int
    skipped: bool


@dataclass
class RolloutReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_prompts: int
    n_samples: int
    # Primary statistic: cross-pair mean prefix between ref and tgt samples.
    mean_inter_pairwise_prefix: float
    mean_reference_intra_prefix: float
    mean_target_intra_prefix: float
    intra_floor_chars: float
    inter_over_intra_floor_ratio: float
    # Secondary modal-vs-modal report for human inspection / forensics.
    mean_inter_modal_prefix_chars: float
    fail_threshold_lt: float
    fail: bool
    per_prompt: list[RolloutPromptComparison]


def _norm_list(samples: list[str]) -> list[str]:
    """Apply Unicode/whitespace normalization to a list of completions.

    Some providers run a safety/rewrite pass that swaps smart quotes,
    em-dashes, or NBSPs into the response. Without normalization a strict
    character-level prefix comparison fires on those rewrites and looks
    identical to a model swap."""
    return [normalize_text(s) for s in samples]


def compare_rollout_prefix(reference: RunResult, target: RunResult) -> RolloutReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    per_prompt: list[RolloutPromptComparison] = []
    inter_pairwise_means: list[float] = []
    inter_modal_chars: list[int] = []
    ref_intra_means: list[float] = []
    tgt_intra_means: list[float] = []

    for idx in sorted(by_idx_ref):
        rp = by_idx_ref[idx]
        tp = by_idx_tgt.get(idx)
        if tp is None:
            continue
        r_samples = _norm_list(rp.completions)
        t_samples = _norm_list(tp.completions)
        if not r_samples or not t_samples:
            per_prompt.append(RolloutPromptComparison(
                prompt_idx=idx,
                name=rp.name,
                n_reference=len(r_samples),
                n_target=len(t_samples),
                reference_intra_prefix_mean=0.0,
                target_intra_prefix_mean=0.0,
                inter_pairwise_prefix_mean=0.0,
                inter_modal_prefix_chars=0,
                skipped=True,
            ))
            continue
        r_modal, _ = modal(r_samples)
        t_modal, _ = modal(t_samples)
        r_intra = _intra_pairwise_prefix(r_samples)
        t_intra = _intra_pairwise_prefix(t_samples)
        inter_pairwise = mean_pairwise_prefix(r_samples, t_samples)
        inter_modal = common_prefix_chars(r_modal, t_modal)
        per_prompt.append(RolloutPromptComparison(
            prompt_idx=idx,
            name=rp.name,
            n_reference=len(r_samples),
            n_target=len(t_samples),
            reference_intra_prefix_mean=round(r_intra, 1),
            target_intra_prefix_mean=round(t_intra, 1),
            inter_pairwise_prefix_mean=round(inter_pairwise, 1),
            inter_modal_prefix_chars=inter_modal,
            skipped=False,
        ))
        inter_pairwise_means.append(inter_pairwise)
        inter_modal_chars.append(inter_modal)
        ref_intra_means.append(r_intra)
        tgt_intra_means.append(t_intra)

    if not inter_pairwise_means:
        return RolloutReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_prompts=0,
            n_samples=reference.n_samples,
            mean_inter_pairwise_prefix=0.0,
            mean_reference_intra_prefix=0.0,
            mean_target_intra_prefix=0.0,
            intra_floor_chars=0.0,
            inter_over_intra_floor_ratio=0.0,
            mean_inter_modal_prefix_chars=0.0,
            fail_threshold_lt=FAIL_RATIO_THRESHOLD,
            fail=False,
            per_prompt=per_prompt,
        )

    inter_pairwise = mean(inter_pairwise_means)
    inter_modal_mean = mean(inter_modal_chars)
    r_intra = mean(ref_intra_means)
    t_intra = mean(tgt_intra_means)
    floor = min(r_intra, t_intra)
    ratio = (inter_pairwise / floor) if floor > 0 else float("inf")
    return RolloutReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_prompts=len(inter_pairwise_means),
        n_samples=reference.n_samples,
        mean_inter_pairwise_prefix=round(inter_pairwise, 1),
        mean_reference_intra_prefix=round(r_intra, 1),
        mean_target_intra_prefix=round(t_intra, 1),
        intra_floor_chars=round(floor, 1),
        inter_over_intra_floor_ratio=round(ratio, 3),
        mean_inter_modal_prefix_chars=round(inter_modal_mean, 1),
        fail_threshold_lt=FAIL_RATIO_THRESHOLD,
        fail=ratio < FAIL_RATIO_THRESHOLD,
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
                        help=f"Samples per prompt (default {DEFAULT_N_SAMPLES})")
    parser.add_argument("--panel-size", type=int, default=len(ROLLOUT_PROMPTS),
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
    panel = list(ROLLOUT_PROMPTS[: args.panel_size])

    n_calls = len(panel) * args.n
    print(
        f"running {TEST_NAME} on {endpoint.label}: "
        f"panel={len(panel)} n={args.n} max_tokens={args.max_tokens} "
        f"=> {n_calls} sequential calls",
        file=sys.stderr,
    )

    result, raw_rows = run_rollout_prefix(
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
