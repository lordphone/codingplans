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
    modal,
    panel_hash,
    utc_stamp,
    write_run_artifacts,
)
from prompts import ARITHMETIC_PANEL_ID, ARITHMETIC_PROMPTS  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "arithmetic"
DEFAULT_N_SAMPLES = 3
DEFAULT_MAX_TOKENS = 50
DEFAULT_SCHEDULE_SEED = 20260425
DEFAULT_SLEEP_RANGE = (1.0, 4.0)
FAIL_THRESHOLD_GAP = 0.05

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
    schedule_seed: int = DEFAULT_SCHEDULE_SEED,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    """Run the arithmetic panel once against `endpoint`.

    Returns `(RunResult, raw_rows)` — the `RunResult` is the comparable
    artifact; `raw_rows` is a per-call forensic log suitable for JSONL.
    """
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
    reference_modal_count: int
    reference_match: bool
    target_modal: int | None
    target_modal_count: int
    target_match: bool


@dataclass
class ArithmeticReport:
    test_name: str
    reference_label: str
    target_label: str
    panel_size: int
    usable_prompts: int
    n_samples: int
    target_modal_accuracy: float
    reference_modal_accuracy: float
    accuracy_gap_ref_minus_target: float
    target_mean_intra_disagreement: float
    reference_mean_intra_disagreement: float
    fail_threshold_gap_gt: float
    fail: bool
    per_prompt: list[ArithmeticPromptComparison]


def _side_stats(completions: list[str]) -> dict | None:
    if not completions:
        return None
    parsed = [_parse_int(c) for c in completions]
    valid = [str(p) for p in parsed if p is not None]
    modal_str, modal_count = modal(valid)
    modal_int = int(modal_str) if modal_str else None
    intra = (len(completions) - modal_count) / len(completions)
    return {"modal": modal_int, "modal_count": modal_count, "intra": intra}


def compare_arithmetic(reference: RunResult, target: RunResult) -> ArithmeticReport:
    """Pure comparison over two `RunResult`s. Raises if incompatible."""
    assert_comparable(reference, target, expected_test=TEST_NAME)

    per_prompt: list[ArithmeticPromptComparison] = []
    ref_correct = 0
    tgt_correct = 0
    ref_intra_sum = 0.0
    tgt_intra_sum = 0.0
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

        rs = _side_stats(rp.completions)
        ts = _side_stats(tp.completions)

        ref_match = bool(rs and rs["modal"] == expected)
        tgt_match = bool(ts and ts["modal"] == expected)
        per_prompt.append(ArithmeticPromptComparison(
            prompt_idx=idx,
            name=rp.name,
            expected=expected,
            digits=digits,
            reference_modal=rs["modal"] if rs else None,
            reference_modal_count=rs["modal_count"] if rs else 0,
            reference_match=ref_match,
            target_modal=ts["modal"] if ts else None,
            target_modal_count=ts["modal_count"] if ts else 0,
            target_match=tgt_match,
        ))
        if rs and ts:
            usable += 1
            ref_correct += int(ref_match)
            tgt_correct += int(tgt_match)
            ref_intra_sum += rs["intra"]
            tgt_intra_sum += ts["intra"]

    if usable == 0:
        return ArithmeticReport(
            test_name=TEST_NAME,
            reference_label=reference.endpoint_label,
            target_label=target.endpoint_label,
            panel_size=reference.panel_size,
            usable_prompts=0,
            n_samples=reference.n_samples,
            target_modal_accuracy=0.0,
            reference_modal_accuracy=0.0,
            accuracy_gap_ref_minus_target=0.0,
            target_mean_intra_disagreement=0.0,
            reference_mean_intra_disagreement=0.0,
            fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
            fail=False,
            per_prompt=per_prompt,
        )

    ref_acc = ref_correct / usable
    tgt_acc = tgt_correct / usable
    gap = ref_acc - tgt_acc
    return ArithmeticReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        panel_size=reference.panel_size,
        usable_prompts=usable,
        n_samples=reference.n_samples,
        target_modal_accuracy=round(tgt_acc, 4),
        reference_modal_accuracy=round(ref_acc, 4),
        accuracy_gap_ref_minus_target=round(gap, 4),
        target_mean_intra_disagreement=round(tgt_intra_sum / usable, 4),
        reference_mean_intra_disagreement=round(ref_intra_sum / usable, 4),
        fail_threshold_gap_gt=FAIL_THRESHOLD_GAP,
        fail=gap > FAIL_THRESHOLD_GAP,
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
                        help="Schedule shuffle seed")
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
