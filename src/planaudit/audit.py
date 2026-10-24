"""Audit one plan endpoint against its provider's official API.

Both sides are sampled in one interleaved schedule, every probe of the tier
is compared, p-values are adjusted across the battery (Benjamini–Hochberg)
and each verdict is judged against the margin calibrated in the lab. The
result is written to data/audits/ as part of the public dataset.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import probes as probe_registry
from . import stats
from .catalog import Audit, Catalog, Endpoint
from .paths import DATA
from .runner import collect

AUDITS = DATA / "audits"
ALPHA = 0.05
MARGIN_SOURCE = DATA / "lab" / "qwen2.5-7b.json"


def lab_margins(path: Path = MARGIN_SOURCE) -> dict[str, float]:
    """Margins calibrated in the lab (largest family), keyed by probe."""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text())
    return {k: v["margin"] for k, v in doc.get("probes", {}).items() if v.get("margin") is not None}


def status_of(verdicts: list[dict[str, Any]]) -> str:
    conclusive = [v for v in verdicts if not v.get("inconclusive") and not v.get("skipped")]
    if not conclusive:
        return "inconclusive"
    if any(v["flagged"] for v in conclusive):
        return "gap"
    return "match"


HEADROOM = 1.25  # same headroom the lab applies to honest-variation effects


async def run_audit(
    cat: Catalog,
    audit: Audit,
    tier: str = "quick",
    *,
    calibrate: bool = False,
    save_runs: bool = True,
) -> dict[str, Any]:
    """Run one tier. With `calibrate`, the reference is sampled twice and the
    reference-vs-reference effect (the in-situ noise floor of that API) widens
    each probe's margin, at the cost of 50% more requests."""
    ref, tgt = cat.endpoint(audit.reference), cat.endpoint(audit.target)
    margins = lab_margins()
    verdicts: list[dict[str, Any]] = []
    started = datetime.now(UTC)
    for name, cfg in probe_registry.TIERS[tier].items():
        probe = probe_registry.make(name, **cfg)
        reason = probe.unusable(ref) or probe.unusable(tgt)
        if reason:
            verdicts.append({"probe": name, "skipped": reason})
            continue
        print(f"[{audit.target}] {name}", file=sys.stderr, flush=True)
        eps = [ref, ref, tgt] if calibrate else [ref, tgt]
        labels = [ref.slug, f"{ref.slug}#twin", tgt.slug] if calibrate else None
        runs = await collect(probe, eps, labels=labels, meta={"audit": audit.plan, "tier": tier})
        r_ref, r_tgt = runs[0], runs[-1]
        if save_runs:
            for r in runs:
                r.save()
        v = probe.compare(r_ref, r_tgt)
        if name in margins:
            v.margin = margins[name]
        if calibrate:
            twin = probe.compare(r_ref, runs[1])
            v.detail["reference_twin_effect"] = twin.effect
            if not twin.inconclusive:
                v.margin = max(v.margin or 0.0, HEADROOM * abs(twin.effect))
        verdicts.append(
            v.to_dict()
            | {
                "title": probe.title,
                "detects": probe.detects,
                "error_rate": {"reference": r_ref.error_rate, "target": r_tgt.error_rate},
                "requests": sum(len(x) for x in r_tgt.items.values()),
            }
        )
    tested = [v for v in verdicts if "skipped" not in v and not v.get("inconclusive")]
    for v, q in zip(tested, stats.benjamini_hochberg([v["p_value"] for v in tested]), strict=True):
        v["q_value"] = q
    for v in verdicts:
        if "skipped" in v:
            continue
        v["flagged"] = bool(
            not v.get("inconclusive")
            and v.get("q_value", 1.0) < ALPHA
            and (v.get("margin") is None or v["effect"] > v["margin"])
        )
    return {
        "plan": audit.plan,
        "target": tgt.public(),
        "reference": ref.public(),
        "tier": tier,
        "calibrated": calibrate,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "alpha": ALPHA,
        "status": status_of(verdicts),
        "verdicts": verdicts,
    }


def publish(result: dict[str, Any]) -> Path:
    day = result["started_at"][:10]
    path = AUDITS / result["plan"] / result["target"]["slug"] / f"{day}_{result['tier']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, default=float))
    return path


def missing_keys(cat: Catalog, audit: Audit) -> list[str]:
    eps: list[Endpoint] = [cat.endpoint(audit.reference), cat.endpoint(audit.target)]
    return [e.api_key_env for e in eps if not e.has_key and e.api_key_env]
