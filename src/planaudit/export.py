"""Write the website's input files under data/.

  data/catalog.json        providers, models, plans, audit pairings (from config/)
  data/audits/index.json   latest audit per (plan, target), newest first
  data/lab/*.json          written by `planaudit lab analyze`

The site only reads data/; it never talks to a database or an API.
"""

from __future__ import annotations

import json
from typing import Any

from . import probes as probe_registry
from .catalog import Catalog, Endpoint
from .paths import DATA


def _endpoint_doc(e: Endpoint) -> dict[str, Any]:
    return e.public() | {
        "logprobs": e.logprobs,
        "thinking_off": e.can_disable_thinking,
        "verified": e.verified,
        "notes": e.notes,
    }


def catalog_doc(cat: Catalog) -> dict[str, Any]:
    """Catalog for the site, including which probes each audit pair can run
    (decided by each probe's own `unusable()`, so the site never guesses)."""
    battery = list(probe_registry.TIERS["standard"])
    forced = {m["slug"] for m in cat.models if m.get("forced_reasoning")}
    audits = []
    for a in cat.audits:
        ref, tgt = cat.endpoints[a.reference], cat.endpoints[a.target]
        runnable = {}
        for name in battery:
            p = probe_registry.PROBES[name]()
            reason = p.unusable(ref) or p.unusable(tgt)
            if reason and "reasoning" in reason:
                reason = (
                    "this model always reasons before answering"
                    if tgt.model in forced
                    else "how to switch reasoning off on this endpoint is not documented yet"
                )
            elif reason and "logprobs" in reason:
                side = "the plan" if ref.logprobs else "the official API"
                reason = f"{side} does not return logprobs"
            runnable[name] = reason
        audits.append(
            {
                "plan": a.plan,
                "target": _endpoint_doc(tgt),
                "reference": _endpoint_doc(ref),
                "probes": runnable,
            }
        )
    return {
        "snapshot": cat.snapshot,
        "fx": cat.fx,
        "providers": cat.providers,
        "models": cat.models,
        "plans": cat.plans,
        "probes": {
            n: {
                "title": probe_registry.PROBES[n].title,
                "detects": probe_registry.PROBES[n].detects,
            }
            for n in battery
        },
        "audits": audits,
    }


def audits_index() -> list[dict[str, Any]]:
    root = DATA / "audits"
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(root.glob("*/*/*.json")):
        doc = json.loads(path.read_text())
        key = (doc["plan"], doc["target"]["slug"])
        entry = {
            "plan": doc["plan"],
            "target": doc["target"]["slug"],
            "model": doc["target"].get("model"),
            "tier": doc["tier"],
            "date": doc["started_at"],
            "status": doc["status"],
            "flagged": [v["probe"] for v in doc["verdicts"] if v.get("flagged")],
            "path": str(path.relative_to(DATA)),
        }
        if key not in latest or entry["date"] > latest[key]["date"]:
            latest[key] = entry
    return sorted(latest.values(), key=lambda e: e["date"], reverse=True)


def export(cat: Catalog) -> list[str]:
    DATA.mkdir(exist_ok=True)
    (DATA / "catalog.json").write_text(json.dumps(catalog_doc(cat), indent=1, ensure_ascii=False))
    (DATA / "audits").mkdir(exist_ok=True)
    (DATA / "audits" / "index.json").write_text(json.dumps({"audits": audits_index()}, indent=1))
    return ["catalog.json", "audits/index.json"]
