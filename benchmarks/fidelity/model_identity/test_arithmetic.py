#!/usr/bin/env python3
"""Test 4 — Arithmetic stress (single-endpoint runner + comparator).

Long multiplication is unusually sensitive to weight quantization because
each digit position depends on near-tied logits over the digit vocabulary.

This file exposes:
  * `run_arithmetic(endpoint, …) -> RunResult` — hits one endpoint, samples
    the panel N times per prompt at T=0, parses an integer from each
    completion, returns a self-describing artifact.
  * `compare_arithmetic(reference, target) -> ArithmeticReport` — pure
    function over two `RunResult`s. No HTTP, no env.
  * CLI: run once against a single endpoint slug. Compare two artifacts
    with `compare.py`.

Usage:
  python benchmarks/fidelity/model_identity/test_arithmetic.py --endpoint glm5-official
  python benchmarks/fidelity/model_identity/test_arithmetic.py --endpoint glm5-alibaba
  python benchmarks/fidelity/compare.py runs/<ref>.summary.json runs/<target>.summary.json
"""

from __future__ import annotations

import argparse
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
    digit_match_rate,
    get_endpoint,
    load_dotenv,
    make_schedule,
    modal,
    panel_hash,
    utc_stamp,
    write_run_artifacts,
)
from prompts import ARITHMETIC_PANEL_ID, ARITHMETIC_PROMPTS  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "arithmetic"
# Research §1: ~20 samples per prompt × ~50 prompts gives ~1000 evaluations
# — enough to detect the 5–15% accuracy gap typical of INT4 on long-form
# math at p<0.01. With panel_size=100, n=20 puts us at 2000 calls per run.
DEFAULT_N_SAMPLES = 20
DEFAULT_MAX_TOKENS = 50
DEFAULT_SCHEDULE_SEED: int | None = None  # random per run; doesn't affect comparability
DEFAULT_SLEEP_RANGE = (1.0, 4.0)
# Per-digit accuracy gap threshold. Per-digit metric is ~10x more sensitive
# than whole-string match, so we tighten the threshold accordingly.
FAIL_THRESHOLD_GAP = 0.02

# Pull a long contiguous digit run, optional thousands-separators tolerated.
_INT_RE = re.compile(r"-?\d[\d,]*")


def _parse_int(content: str) -> int | None:
    """Best-effort integer extraction from a free-form completion.

    We don't enforce any format on the model, so quantization differences in
    surrounding prose don't masquerade as arithmetic errors. We pick the
    longest digit run in the response and strip thousands separators.
    """
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


def run_arithmetic(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = ARITHMETIC_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the arithmetic panel once against `endpoint`.

    Returns `(RunResult, raw_rows)` — the `RunResult` is the comparable
    artifact; `raw_rows` is a per-call forensic log suitable for JSONL.

    `schedule_seed=None` means "pick a fresh random seed per run." The
    framework treats `schedule_seed` as a stealth knob (does not affect
    comparability), so randomizing it defeats string-hash benchmark
    detectors that look for the same call ordering on every run.
    """
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
            parsed = _parse_int(resp.content)
            expected = item.meta["expected"]
            raw_rows.append({
                "i": i,
                "prompt_idx": call.prompt_idx,
                "prompt_name": item.name,
                "sample_idx": call.sample_idx,
                "completion_tokens": resp.completion_tokens,
                "latency_s": round(resp.latency_s, 4),
                "content": resp.content[:200],
                "parsed_int": parsed,
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
        panel_id=ARITHMETIC_PANEL_ID,
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
class ArithmeticPromptComparison:
    prompt_idx: int
    name: str
    expected: int
    digits: int
    reference_modal: int | None
    reference_modal_freq: float
    reference_modal_match: bool
    reference_digit_accuracy: float
    target_modal: int | None
    target_modal_freq: float
    target_modal_match: bool
    target_digit_accuracy: float


@dataclass
class ArithmeticReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_prompts: int
    n_samples: int
    # Primary signal (research §1: ~10x more sensitive than whole-string match)
    reference_digit_accuracy: float
    target_digit_accuracy: float
    digit_accuracy_gap_ref_minus_target: float
    # Where in the answer the gap concentrates: research §1 notes the last
    # digit is hardest under quantization (cascading carries), the first
    # digit is most often confidently correct.
    reference_first_digit_accuracy: float
    target_first_digit_accuracy: float
    reference_last_digit_accuracy: float
    target_last_digit_accuracy: float
    # Whole-string secondary metric, kept for human readability
    reference_modal_accuracy: float
    target_modal_accuracy: float
    accuracy_gap_ref_minus_target: float
    # Mean modal-frequency across prompts. Research §1: "a stable mode at
    # lower frequency is itself a quantization signature" — flatter logits
    # break ties more often even at T=0, so the mode wins by less.
    reference_mean_modal_freq: float
    target_mean_modal_freq: float
    fail_threshold_gap_gt: float
    fail: bool
    per_prompt: list[ArithmeticPromptComparison]


def _side_stats(completions: list[str], expected: int) -> dict | None:
    """Aggregate per-prompt stats from one side's completions.

    Computes:
      modal answer + frequency (mode-count / n_samples),
      mean per-digit accuracy across all completions (the primary signal),
      first-digit and last-digit accuracy,
      whole-string modal-match flag.
    """
    if not completions:
        return None
    parsed = [_parse_int(c) for c in completions]
    valid_strs = [str(p) for p in parsed if p is not None]
    if not valid_strs:
        return {
            "modal": None, "modal_freq": 0.0, "modal_match": False,
            "digit_acc": 0.0, "first_acc": 0.0, "last_acc": 0.0,
        }
    modal_str, modal_count = modal(valid_strs)
    modal_int = int(modal_str) if modal_str else None
    modal_freq = modal_count / len(completions)
    n = len(parsed)
    digit_total = 0.0
    first_total = 0
    last_total = 0
    counted = 0
    for p in parsed:
        rate, first_ok, last_ok = digit_match_rate(p, expected)
        digit_total += rate
        first_total += int(first_ok)
        last_total += int(last_ok)
        counted += 1
    return {
        "modal": modal_int,
        "modal_freq": modal_freq,
        "modal_match": modal_int == expected,
        "digit_acc": digit_total / n,
        "first_acc": first_total / n,
        "last_acc": last_total / n,
    }


def compare_arithmetic(reference: RunResult, target: RunResult) -> ArithmeticReport:
    """Pure comparison over two `RunResult`s. Raises if incompatible.

    Primary fail signal is the per-digit accuracy gap (research §1: ~10x
    more sensitive than whole-string match and shows *where* in the answer
    the model fails). Whole-string modal accuracy and mean modal-frequency
    are reported as corroborating signals.
    """
    assert_comparable(reference, target, expected_test=TEST_NAME)

    per_prompt: list[ArithmeticPromptComparison] = []
    ref_digit_sum = 0.0
    tgt_digit_sum = 0.0
    ref_modal_correct = 0
    tgt_modal_correct = 0
    ref_modal_freq_sum = 0.0
    tgt_modal_freq_sum = 0.0
    ref_first_sum = 0.0
    tgt_first_sum = 0.0
    ref_last_sum = 0.0
    tgt_last_sum = 0.0
    usable = 0

    by_idx_ref = {p.prompt_idx: p for p in reference.prompts}
    by_idx_tgt = {p.prompt_idx: p for p in target.prompts}

    for idx in sorted(by_idx_ref):
        rp = by_idx_ref[idx]
        tp = by_idx_tgt.get(idx)
        if tp is None:
            continue
        meta = rp.meta or {}
        expected = int(meta.get("expected"))
        digits = int(meta.get("digits", 0))

        rs = _side_stats(rp.completions, expected)
        ts = _side_stats(tp.completions, expected)

        per_prompt.append(ArithmeticPromptComparison(
            prompt_idx=idx,
            name=rp.name,
            expected=expected,
            digits=digits,
            reference_modal=rs["modal"] if rs else None,
            reference_modal_freq=round(rs["modal_freq"], 4) if rs else 0.0,
            reference_modal_match=bool(rs and rs["modal_match"]),
            reference_digit_accuracy=round(rs["digit_acc"], 4) if rs else 0.0,
            target_modal=ts["modal"] if ts else None,
            target_modal_freq=round(ts["modal_freq"], 4) if ts else 0.0,
            target_modal_match=bool(ts and ts["modal_match"]),
            target_digit_accuracy=round(ts["digit_acc"], 4) if ts else 0.0,
        ))
        if rs and ts:
            usable += 1
            ref_digit_sum += rs["digit_acc"]
            tgt_digit_sum += ts["digit_acc"]
            ref_modal_correct += int(rs["modal_match"])
            tgt_modal_correct += int(ts["modal_match"])
            ref_modal_freq_sum += rs["modal_freq"]
            tgt_modal_freq_sum += ts["modal_freq"]
            ref_first_sum += rs["first_acc"]
            tgt_first_sum += ts["first_acc"]
            ref_last_sum += rs["last_acc"]
            tgt_last_sum += ts["last_acc"]

    if usable == 0:
        return ArithmeticReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_prompts=0,
            n_samples=reference.n_samples,
            reference_digit_accuracy=0.0,
            target_digit_accuracy=0.0,
            digit_accuracy_gap_ref_minus_target=0.0,
            reference_first_digit_accuracy=0.0,
            target_first_digit_accuracy=0.0,
            reference_last_digit_accuracy=0.0,
            target_last_digit_accuracy=0.0,
            reference_modal_accuracy=0.0,
            target_modal_accuracy=0.0,
            accuracy_gap_ref_minus_target=0.0,
            reference_mean_modal_freq=0.0,
            target_mean_modal_freq=0.0,
            fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
            fail=False,
            per_prompt=per_prompt,
        )

    ref_digit = ref_digit_sum / usable
    tgt_digit = tgt_digit_sum / usable
    digit_gap = ref_digit - tgt_digit
    ref_modal_acc = ref_modal_correct / usable
    tgt_modal_acc = tgt_modal_correct / usable
    return ArithmeticReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_prompts=usable,
        n_samples=reference.n_samples,
        reference_digit_accuracy=round(ref_digit, 4),
        target_digit_accuracy=round(tgt_digit, 4),
        digit_accuracy_gap_ref_minus_target=round(digit_gap, 4),
        reference_first_digit_accuracy=round(ref_first_sum / usable, 4),
        target_first_digit_accuracy=round(tgt_first_sum / usable, 4),
        reference_last_digit_accuracy=round(ref_last_sum / usable, 4),
        target_last_digit_accuracy=round(tgt_last_sum / usable, 4),
        reference_modal_accuracy=round(ref_modal_acc, 4),
        target_modal_accuracy=round(tgt_modal_acc, 4),
        accuracy_gap_ref_minus_target=round(ref_modal_acc - tgt_modal_acc, 4),
        reference_mean_modal_freq=round(ref_modal_freq_sum / usable, 4),
        target_mean_modal_freq=round(tgt_modal_freq_sum / usable, 4),
        fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
        fail=digit_gap > FAIL_THRESHOLD_GAP,
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
    parser.add_argument("--panel-size", type=int, default=len(ARITHMETIC_PROMPTS),
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
    panel = list(ARITHMETIC_PROMPTS[: args.panel_size])

    n_calls = len(panel) * args.n
    print(
        f"running {TEST_NAME} on {endpoint.label}: "
        f"panel={len(panel)} n={args.n} max_tokens={args.max_tokens} "
        f"=> {n_calls} sequential calls",
        file=sys.stderr,
    )

    result, raw_rows = run_arithmetic(
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
