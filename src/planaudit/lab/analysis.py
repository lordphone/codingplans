"""Turn lab runs into calibrated margins and detection-power curves.

For each family, every variant is compared against the family's reference
deployment with every probe:

  margin      The largest effect any *honest* variant produced on that probe,
              plus 25% headroom (floored at the probe's default margin).
              This is what "material difference" means: bigger than legitimate
              serving differences (restarts, fp16, kernels) ever produce.
              Honest variants are scored against a leave-one-out margin
              computed from the *other* honest variants, so their false-alarm
              rate is not trivially zero.
  power       Detection rate (p < alpha AND effect > margin) when only a random
              subset of n items is used, over many random subsets, for growing
              n. The x-axis is reported in requests, i.e. what an audit costs.

Writes data/lab/<family>.json and data/lab/index.json.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .. import probes as probe_registry
from ..paths import DATA
from .config import Family, Lab
from .experiment import load_run

ALPHA = 0.05
HEADROOM = 1.25
BUDGETS = [5, 10, 20, 40, 80, 160, 320]


def _budgets(n: int) -> list[int]:
    out = [b for b in BUDGETS if b < n]
    return [*out, n]


def _pair(args: tuple) -> dict[str, Any]:
    fam_id, ref_id, var_id, probe_name, cfg, subsamples, B = args
    probe = probe_registry.make(probe_name, **cfg)
    ref, run = load_run(fam_id, ref_id, probe_name), load_run(fam_id, var_id, probe_name)
    full = probe.compare(ref, run, B=max(B, 2000))
    out: dict[str, Any] = {
        "variant": var_id,
        "probe": probe_name,
        "effect": full.effect,
        "p_value": full.p_value,
        "n_items": full.n_items,
        "inconclusive": full.inconclusive,
        "detail": full.detail,
        "reference": full.reference,
        "target": full.target,
        "error_rate": run.error_rate,
        "curve": [],
    }
    if full.inconclusive:
        return out
    ids = sorted(set(ref.items) & set(run.items))
    per_item = max(1, len(next(iter(run.items.values()))))
    g = np.random.default_rng(0)
    for n in _budgets(len(ids)):
        draws = 1 if n == len(ids) else subsamples
        pts = []
        for s in range(draws):
            sub = list(g.choice(ids, size=n, replace=False))
            v = probe.compare(ref, run, sub, B=B, seed=s)
            if not v.inconclusive:
                pts.append((v.effect, v.p_value))
        out["curve"].append({"items": n, "requests": n * per_item, "draws": pts})
    return out


def _rate(draws: list[tuple[float, float]], margin: float | None) -> float | None:
    if not draws:
        return None
    hits = [p < ALPHA and (margin is None or e > margin) for e, p in draws]
    return float(np.mean(hits))


def analyze_family(
    lab: Lab, fam: Family, *, subsamples: int = 100, B: int = 300, workers: int = 8
) -> dict[str, Any]:
    probes_cfg = lab.probes_for(fam)
    jobs = []
    for v in fam.variants:
        if v.id == fam.reference:
            continue
        for name, cfg in probes_cfg.items():
            if load_run(fam.id, fam.reference, name) and load_run(fam.id, v.id, name):
                jobs.append((fam.id, fam.reference, v.id, name, cfg, subsamples, B))
    print(f"[{fam.id}] analysing {len(jobs)} variant×probe pairs", file=sys.stderr, flush=True)
    if workers <= 1:
        pairs = [_pair(j) for j in jobs]
    else:
        with ProcessPoolExecutor(workers) as pool:
            pairs = list(pool.map(_pair, jobs))

    kind = {v.id: v for v in fam.variants}
    honest = {
        (r["variant"], r["probe"]): r["effect"]
        for r in pairs
        if kind[r["variant"]].kind == "honest" and not r["inconclusive"]
    }

    def margin(probe: str, exclude: str | None = None) -> float | None:
        floor = probe_registry.PROBES[probe].default_margin
        hs = [abs(e) for (v, p), e in honest.items() if p == probe and v != exclude]
        if not hs:
            return floor
        m = HEADROOM * max(hs)
        return max(m, floor) if floor is not None else m

    results = []
    for r in pairs:
        v = kind[r["variant"]]
        m = margin(r["probe"], exclude=v.id if v.kind == "honest" else None)
        curve = [
            {
                "items": c["items"],
                "requests": c["requests"],
                "rate": _rate(c["draws"], m),
                "rate_significance_only": _rate(c["draws"], None),
                "median_effect": float(np.median([e for e, _ in c["draws"]]))
                if c["draws"]
                else None,
            }
            for c in r["curve"]
        ]
        flagged = not r["inconclusive"] and r["p_value"] < ALPHA and (m is None or r["effect"] > m)
        min_req = next((c["requests"] for c in curve if (c["rate"] or 0) >= 0.95), None)
        results.append(
            {k: r[k] for k in r if k != "curve"}
            | {"margin": m, "flagged": flagged, "curve": curve, "requests_for_95": min_req}
        )

    ref_meta = {}
    for name in probes_cfg:
        if run := load_run(fam.id, fam.reference, name):
            ref_meta = run.meta
            break
    return {
        "family": fam.id,
        "name": fam.name,
        "params_b": fam.params_b,
        "reference": fam.reference,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": {"vllm": ref_meta.get("vllm"), "gpu": ref_meta.get("gpu")},
        "alpha": ALPHA,
        "headroom": HEADROOM,
        "variants": [
            {
                "id": v.id,
                "kind": v.kind,
                "cut": v.cut,
                "label": v.label,
                "model": v.model,
                "args": list(v.args),
                "proxy": v.proxy,
            }
            for v in fam.variants
        ],  # fmt: skip
        "probes": {
            n: {
                "title": probe_registry.PROBES[n].title,
                "detects": probe_registry.PROBES[n].detects,
                "effect_name": probe_registry.PROBES[n].effect_name,
                "margin": margin(n),
                "config": probes_cfg[n],
            }
            for n in probes_cfg
        },
        "results": results,
    }


def analyze(lab: Lab, families: list[str] | None = None, **kw: Any) -> list[str]:
    out_dir = DATA / "lab"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for fam in lab.families:
        if families and fam.id not in families:
            continue
        if load_run(fam.id, fam.reference, next(iter(lab.probes_for(fam)))) is None:
            print(f"[{fam.id}] no reference runs yet; skipping", file=sys.stderr)
            continue
        doc = analyze_family(lab, fam, **kw)
        path = out_dir / f"{fam.id}.json"
        path.write_text(json.dumps(doc, indent=1, default=float))
        written.append(fam.id)
    index = sorted(p.stem for p in out_dir.glob("*.json") if p.stem != "index")
    (out_dir / "index.json").write_text(json.dumps({"families": index}, indent=1))
    return written
