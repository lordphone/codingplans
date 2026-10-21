#!/usr/bin/env python3
"""Response caching — is the plan replaying old answers instead of generating?

A cheap way to serve more users on fewer GPUs is an answer cache: exact
(keyed on the request bytes) or semantic (keyed on an embedding of the
prompt). Both are invisible on a single request and obvious statistically:

  * Entropy probes — prompts at T=1 whose honest answers are essentially
    never identical twice ("generate a random key"). The official API's
    duplicate rate is ~0; a cached endpoint repeats itself.
  * Nonce probes — each call carries a fresh random ticket id that the
    reply must echo. A prefix/semantic cache returns a reply that echoes
    an *older* nonce (or none), which no honest model would do.

Duplicate replies are also tagged with their TTFT in the JSONL log, since
cache hits typically return much faster than fresh generations.

Usage:
  python benchmarks/fidelity/integrity/test_response_cache.py --endpoint glm5-official
"""

from __future__ import annotations

import re
import secrets
import string
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

_HERE = Path(__file__).resolve().parent
_FIDELITY_DIR = _HERE.parent
for _p in (_FIDELITY_DIR, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from framework import (  # noqa: E402
    ChatRequest,
    ChatResponse,
    Endpoint,
    PromptItem,
    RunResult,
    assert_comparable,
    normalize_text,
    run_panel,
    standard_cli,
)
from integrity_prompts import CACHE_PANEL_ID, CACHE_PROMPTS  # noqa: E402
from stats import two_proportion_test  # noqa: E402

RUNS_DIR = _HERE / "runs"

TEST_NAME = "response_cache"
DEFAULT_N_SAMPLES = 8
DEFAULT_MAX_TOKENS = 200
DEFAULT_SLEEP_RANGE = (1.0, 4.0)
TEMPERATURE = 1.0

ALPHA = 0.05
DUPLICATE_GAP_THRESHOLD = 0.10
NONCE_GAP_THRESHOLD = 0.10
MIN_SAMPLES_PER_SIDE = 12

_NONCE_ALPHABET = string.ascii_uppercase + string.digits


def _new_nonce() -> str:
    return "OPS-" + "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(6))


_NONCE_RE = re.compile(r"OPS-[A-Z0-9]{6}")


def nonce_outcome(content: str, nonce: str) -> str:
    """'ok' when the reply echoes this call's nonce, 'stale' when it echoes a
    different well-formed nonce (the cache signature), 'missing' otherwise."""
    found = _NONCE_RE.findall(content[:300])
    if nonce in found:
        return "ok"
    if found:
        return "stale"
    return "missing"


def run_response_cache(
    endpoint: Endpoint,
    *,
    panel: Sequence[PromptItem] = CACHE_PROMPTS,
    n_samples: int = DEFAULT_N_SAMPLES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    schedule_seed: int | None = None,
    sleep_range: tuple[float, float] = DEFAULT_SLEEP_RANGE,
    progress: bool = True,
) -> tuple[RunResult, list[dict]]:
    # Calls are strictly sequential, so the nonce issued by `build` is the
    # one `record` must look for.
    state: dict[str, str | None] = {"nonce": None}

    def build(item: PromptItem, _k: int) -> ChatRequest:
        messages = item.messages
        state["nonce"] = None
        if (item.meta or {}).get("probe") == "nonce":
            nonce = _new_nonce()
            state["nonce"] = nonce
            messages = tuple(
                {**m, "content": m["content"].replace("{nonce}", nonce)} if m.get("role") == "user" else m
                for m in messages
            )
        return ChatRequest(messages=messages, temperature=TEMPERATURE, max_tokens=max_tokens)

    def record(item: PromptItem, resp: ChatResponse) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "probe": (item.meta or {}).get("probe"),
            "normalized": normalize_text(resp.content).strip().casefold(),
            "ttft_s": resp.ttft_s,
        }
        if state["nonce"] is not None:
            rec["nonce"] = state["nonce"]
            rec["nonce_outcome"] = nonce_outcome(resp.content, state["nonce"])
        return rec

    return run_panel(
        endpoint,
        test_name=TEST_NAME,
        panel_id=CACHE_PANEL_ID,
        panel=panel,
        n_samples=n_samples,
        max_tokens=max_tokens,
        schedule_seed=schedule_seed,
        sleep_range=sleep_range,
        build_request=build,
        record=record,
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class ResponseCacheReport:
    test_name: str
    reference_label: str
    target_label: str
    reference_duplicate_rate: float
    target_duplicate_rate: float
    duplicate_p_value: float
    reference_nonce_ok_rate: float
    target_nonce_ok_rate: float
    target_stale_nonces: int
    nonce_p_value: float
    metric: str
    reference_value: float
    target_value: float
    p_value: float
    inconclusive: bool
    fail: bool


def _duplicates(run: RunResult) -> tuple[int, int]:
    """(samples that repeat an earlier sample of the same prompt, total samples)
    over the entropy probes."""
    dup = total = 0
    for p in run.prompts:
        if (p.meta or {}).get("probe") != "entropy":
            continue
        counts = Counter(r["normalized"] for r in p.records if r.get("normalized"))
        dup += sum(c - 1 for c in counts.values())
        total += sum(counts.values())
    return dup, total


def _nonce(run: RunResult) -> tuple[int, int, int]:
    outcomes = [r.get("nonce_outcome") for p in run.prompts for r in p.records if "nonce_outcome" in r]
    return outcomes.count("ok"), outcomes.count("stale"), len(outcomes)


def compare_response_cache(reference: RunResult, target: RunResult) -> ResponseCacheReport:
    assert_comparable(reference, target, expected_test=TEST_NAME)
    r_dup, r_tot = _duplicates(reference)
    t_dup, t_tot = _duplicates(target)
    dup_gap, dup_p = two_proportion_test(t_dup, t_tot, r_dup, r_tot)
    r_ok, _, r_n = _nonce(reference)
    t_ok, t_stale, t_n = _nonce(target)
    nonce_gap, nonce_p = two_proportion_test(r_ok, r_n, t_ok, t_n)

    inconclusive = min(r_tot, t_tot) < MIN_SAMPLES_PER_SIDE
    fail = (not inconclusive) and (
        (dup_gap > DUPLICATE_GAP_THRESHOLD and dup_p < ALPHA / 2)
        or (nonce_gap > NONCE_GAP_THRESHOLD and nonce_p < ALPHA / 2)
        # A stale nonce has no innocent explanation.
        or t_stale > 0
    )
    t_rate = t_dup / t_tot if t_tot else 0.0
    r_rate = r_dup / r_tot if r_tot else 0.0
    return ResponseCacheReport(
        test_name=TEST_NAME,
        reference_label=reference.endpoint_label,
        target_label=target.endpoint_label,
        reference_duplicate_rate=round(r_rate, 4),
        target_duplicate_rate=round(t_rate, 4),
        duplicate_p_value=dup_p,
        reference_nonce_ok_rate=round(r_ok / r_n, 4) if r_n else 0.0,
        target_nonce_ok_rate=round(t_ok / t_n, 4) if t_n else 0.0,
        target_stale_nonces=t_stale,
        nonce_p_value=nonce_p,
        metric="duplicate_rate_at_t1",
        reference_value=round(r_rate, 4),
        target_value=round(t_rate, 4),
        p_value=min(1.0, 2 * min(dup_p, nonce_p)),
        inconclusive=inconclusive,
        fail=fail,
    )


def main() -> int:
    return standard_cli(
        description=__doc__.splitlines()[0],
        test_name=TEST_NAME,
        panel=CACHE_PROMPTS,
        run=run_response_cache,
        runs_dir=RUNS_DIR,
        default_n=DEFAULT_N_SAMPLES,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        default_sleep=DEFAULT_SLEEP_RANGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
