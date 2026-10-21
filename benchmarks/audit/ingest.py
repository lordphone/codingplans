"""Write audit and performance results to Supabase (PostgREST, service role).

Needs SUPABASE_URL (https://<ref>.supabase.co) and SUPABASE_SERVICE_ROLE_KEY.
The service-role key bypasses RLS — it only ever lives in `.env` / CI
secrets, never in the web app.

Slugs are resolved to ids here: provider_slug + plan_slug → plans.id and
model_slug → models.id. A missing catalog row is a hard error with a hint to
seed the catalog (supabase/seed.sql) — results are never silently dropped.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

__all__ = ["SupabaseWriter", "ingest_audit_rows", "ingest_benchmark_rows"]


class SupabaseWriter:
    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        url = url or os.environ.get("SUPABASE_URL", "").strip()
        key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set to ingest")
        self._rest = url.rstrip("/") + "/rest/v1"
        self._http = httpx.Client(timeout=30.0, headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        self._plan_ids: dict[tuple[str, str], str] = {}
        self._model_ids: dict[str, str] = {}

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        r = self._http.get(f"{self._rest}/{table}", params=params)
        r.raise_for_status()
        return r.json()

    def plan_id(self, provider_slug: str, plan_slug: str) -> str:
        key = (provider_slug, plan_slug)
        if key not in self._plan_ids:
            rows = self._get("plans", {
                "select": "id,providers!inner(slug)",
                "slug": f"eq.{plan_slug}",
                "providers.slug": f"eq.{provider_slug}",
            })
            if not rows:
                raise SystemExit(
                    f"no plan {provider_slug}/{plan_slug} in Supabase — add it to supabase/seed.sql "
                    "and run it (see docs/REQUIREMENTS.md)"
                )
            self._plan_ids[key] = rows[0]["id"]
        return self._plan_ids[key]

    def model_id(self, model_slug: str) -> str:
        if model_slug not in self._model_ids:
            rows = self._get("models", {"select": "id", "slug": f"eq.{model_slug}"})
            if not rows:
                raise SystemExit(f"no model {model_slug!r} in Supabase — add it to supabase/seed.sql")
            self._model_ids[model_slug] = rows[0]["id"]
        return self._model_ids[model_slug]

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        r = self._http.post(f"{self._rest}/{table}", json=rows,
                            headers={"Prefer": "return=minimal"})
        if r.status_code >= 400:
            raise SystemExit(f"insert into {table} failed: HTTP {r.status_code} {r.text[:400]}")


def _details(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the stored report small: drop per-prompt/per-cell arrays (they
    stay in the local report JSON) and keep scalar fields."""
    rep = row.get("report") or {}
    slim = {k: v for k, v in rep.items() if not isinstance(v, list) or k in ("regressions", "probes")}
    return {
        "report": slim,
        "reference_artifact": row.get("reference_artifact"),
        "target_artifact": row.get("target_artifact"),
    }


def ingest_audit_rows(rows: list[dict[str, Any]], writer: SupabaseWriter | None = None) -> None:
    w = writer or SupabaseWriter()
    out = []
    for r in rows:
        out.append({
            "plan_id": w.plan_id(r["provider_slug"], r["plan_slug"]),
            "model_id": w.model_id(r["model_slug"]),
            "test_name": r["test_name"],
            "family": r["family"],
            "status": r["status"],
            "metric": r.get("metric"),
            "reference_value": r.get("reference_value"),
            "target_value": r.get("target_value"),
            "p_value": r.get("p_value"),
            "q_value": r.get("q_value"),
            "summary": r.get("summary"),
            "reference_label": r["reference_label"],
            "target_label": r["target_label"],
            "panel_id": r.get("panel_id"),
            "details": _details(r),
        })
    w.insert("audit_results", out)
    print(f"ingested {len(out)} audit_results rows", file=sys.stderr)


def ingest_benchmark_rows(rows: list[dict[str, Any]], writer: SupabaseWriter | None = None) -> None:
    """rows: {provider_slug, plan_slug, model_slug, tps, ttft_s, samples,
    error_rate, tps_p10, ttft_p90_s}"""
    w = writer or SupabaseWriter()
    out = []
    for r in rows:
        out.append({
            "plan_id": w.plan_id(r["provider_slug"], r["plan_slug"]),
            "model_id": w.model_id(r["model_slug"]),
            **{k: r.get(k) for k in ("tps", "ttft_s", "samples", "error_rate", "tps_p10", "ttft_p90_s")},
        })
    w.insert("benchmark_runs", out)
    print(f"ingested {len(out)} benchmark_runs rows", file=sys.stderr)
