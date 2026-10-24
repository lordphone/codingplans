"""Write the website's input files under data/.

  data/catalog.json        providers, models, plans, audit pairings (from config/)
  data/audits/index.json   latest audit per (plan, target), newest first
  data/lab/*.json          written by `planaudit lab analyze`

The site only reads data/; it never talks to a database or an API.
"""

from __future__ import annotations

import json
from typing import Any

from .catalog import Catalog
from .paths import DATA


def catalog_doc(cat: Catalog) -> dict[str, Any]:
    return {
        "snapshot": cat.snapshot,
        "providers": cat.providers,
        "models": cat.models,
        "plans": cat.plans,
        "audits": [
            {
                "plan": a.plan,
                "target": cat.endpoints[a.target].public(),
                "reference": cat.endpoints[a.reference].public(),
            }
            for a in cat.audits
        ],
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
