#!/usr/bin/env python3
"""Speed probe for every audited plan endpoint → `benchmark_runs` rows.

For each plan endpoint in endpoints.json `audits`, issues --samples sequential
streamed requests with random coding scenarios (benchmarks/performance/
scenarios.py), then summarizes them into one row: median TPS, median TTFT,
p10 TPS (the slow tail users feel), p90 TTFT, error rate and sample count.

Scheduling this several times a day (the GitHub workflow does) is what
surfaces peak-hour throttling: compare rows by hour on the plan page.

  python benchmarks/audit/run_performance.py --dry-run
  python benchmarks/audit/run_performance.py --samples 5 --ingest
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from statistics import median, quantiles
from typing import Any

_HERE = Path(__file__).resolve().parent
_BENCH = _HERE.parent
for _p in (_BENCH / "fidelity", _BENCH / "performance", _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from benchmark import BenchmarkJob, run_benchmark  # noqa: E402
from client import HONEST_USER_AGENT  # noqa: E402
from framework import load_dotenv  # noqa: E402
from scenarios import pick_scenario  # noqa: E402
from targets import ENDPOINTS, load_audits  # noqa: E402


def _pct(values: list[float], q: int) -> float | None:
    """q-th percentile (1..99) with the inclusive method; None if <2 values."""
    if len(values) < 2:
        return values[0] if values else None
    return quantiles(values, n=100, method="inclusive")[q - 1]


def probe(endpoint_slug: str, samples: int, sleep: tuple[float, float]) -> dict[str, Any]:
    ep = ENDPOINTS[endpoint_slug]
    ok: list[dict[str, Any]] = []
    errors = 0
    for i in range(samples):
        sc = pick_scenario()
        headers = dict(sc.extra_headers)
        if ep.honest_user_agent:
            headers = {"User-Agent": HONEST_USER_AGENT}
        body_extra = dict(ep.extra_params)
        # Speed is measured on the default (agent) configuration; reasoning
        # time counts as part of the wait the user experiences.
        job = BenchmarkJob(
            provider_id=endpoint_slug, base_url=ep.base_url, api_key=ep.api_key() or "",
            model=ep.model, prompt="", max_tokens=512, timeout_s=180.0, stream_usage=True,
            extra_params=body_extra or None, extra_headers=headers,
            messages=sc.messages, scenario_name=sc.name,
        )
        try:
            ok.append(run_benchmark(job))
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  {endpoint_slug} sample {i}: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
        if i < samples - 1:
            time.sleep(random.uniform(*sleep))
    tps = [r["output_tps"] for r in ok]
    ttft = [r["ttft_s"] for r in ok]
    return {
        "tps": round(median(tps), 2) if tps else None,
        "ttft_s": round(median(ttft), 3) if ttft else None,
        "tps_p10": round(_pct(tps, 10), 2) if tps else None,
        "ttft_p90_s": round(_pct(ttft, 90), 3) if ttft else None,
        "samples": samples,
        "error_rate": round(errors / samples, 4) if samples else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--sleep-min", type=float, default=3.0)
    parser.add_argument("--sleep-max", type=float, default=12.0)
    parser.add_argument("--target", help="Only this plan endpoint slug")
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_dotenv()

    rows: list[dict[str, Any]] = []
    for g in load_audits():
        for t in g.targets:
            if args.target not in (None, t.endpoint):
                continue
            ep = ENDPOINTS[t.endpoint]
            if args.dry_run:
                print(f"{t.endpoint}: {ep.model} @ {ep.base_url} key "
                      f"{ep.api_key_env}={'set' if ep.api_key() else 'MISSING'}")
                continue
            if ep.api_key() is None:
                print(f"skip {t.endpoint}: {ep.api_key_env} not set", file=sys.stderr)
                continue
            print(f"probing {t.endpoint} ({args.samples} samples)", file=sys.stderr)
            stats = probe(t.endpoint, args.samples, (args.sleep_min, args.sleep_max))
            row = {"provider_slug": t.provider_slug, "plan_slug": t.plan_slug,
                   "model_slug": g.model_slug, "endpoint": t.endpoint, **stats}
            print(json.dumps(row))
            if stats["tps"] is not None:
                rows.append(row)

    if args.ingest and rows:
        from ingest import ingest_benchmark_rows

        ingest_benchmark_rows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
