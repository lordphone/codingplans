"""Endpoint registry for fidelity audits.

Each `Endpoint` is a single OpenAI-compatible chat target. The fidelity tests
take **one** endpoint at a time (see `benchmarks/fidelity/model_identity/`), so this
file is a flat registry — no notion of "pair." Comparison is a separate step
that joins two run artifacts; which plan is audited against which official
reference lives in the `audits` section of the same JSON file.

Endpoints are data, not code: they are loaded from `benchmarks/endpoints.json`
(see the `_comment` there for the field reference).

Adding a new endpoint:
  1. Add an entry under `endpoints` with a stable filename-safe slug.
  2. Pick a stable `api_key_env` name; document it in `.env.example` and
     `docs/REQUIREMENTS.md`.
  3. If it is a plan, add it to (or create) the matching `audits` group.
  4. Run `python benchmarks/audit/preflight.py --endpoint <slug>` and flip
     `verified` to true once the model id and URL are confirmed.

Convention: `<model-short>-<provider-slug>`, e.g. `glm5-official`,
`glm5-alibaba`. Reference (vendor) endpoints get `-official`; everything else
takes the provider's slug.

All base URLs and model ids can be overridden per-environment via
`<SLUG>_BASE_URL` / `<SLUG>_MODEL` (slug upper-cased, `-` and `.` → `_`) —
useful when a vendor moves hosts or renames a model.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "AuditGroup",
    "AuditTarget",
    "ENDPOINTS",
    "ENDPOINTS_JSON",
    "Endpoint",
    "load_audits",
    "get_endpoint",
]

# CODINGPLANS_ENDPOINTS_JSON points the whole suite at another registry
# (used by benchmarks/selftest.py --e2e to target a local fake API).
ENDPOINTS_JSON = Path(
    os.environ.get("CODINGPLANS_ENDPOINTS_JSON")
    or Path(__file__).resolve().parent.parent / "endpoints.json"
)


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is not None and v.strip():
        return v.strip()
    return None


def env_prefix(slug: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", slug).upper()


@dataclass(frozen=True)
class Endpoint:
    """One OpenAI-compatible chat endpoint.

    `label` is a short human-readable id used in artifact filenames and
    summary metadata. `extra_params` is merged into every request body sent
    to this endpoint. `thinking_on` / `thinking_off` are merged when a test
    explicitly asks for reasoning on or off (`ChatRequest.thinking`);
    `thinking_off=None` means the model cannot disable thinking and such a
    request is sent without any toggle.
    """

    label: str
    base_url: str
    api_key_env: str
    model: str
    extra_params: dict[str, Any] = field(default_factory=dict)
    role: str = "official"
    thinking_on: dict[str, Any] | None = None
    thinking_off: dict[str, Any] | None = None
    honest_user_agent: bool = False
    verified: bool = False

    def api_key(self) -> str | None:
        return _env(self.api_key_env)


@dataclass(frozen=True)
class AuditTarget:
    endpoint: str
    provider_slug: str
    plan_slug: str


@dataclass(frozen=True)
class AuditGroup:
    model_slug: str
    reference: str
    targets: tuple[AuditTarget, ...]


def _load_raw(path: Path = ENDPOINTS_JSON) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _endpoint_from(slug: str, raw: dict[str, Any]) -> Endpoint:
    prefix = env_prefix(slug)
    thinking = raw.get("thinking") or {}
    return Endpoint(
        label=slug,
        base_url=_env(f"{prefix}_BASE_URL") or raw["base_url"],
        api_key_env=_env(f"{prefix}_API_KEY_ENV") or raw["api_key_env"],
        model=_env(f"{prefix}_MODEL") or raw["model"],
        extra_params=dict(raw.get("extra_params") or {}),
        role=str(raw.get("role", "official")),
        thinking_on=thinking.get("on"),
        thinking_off=thinking.get("off"),
        honest_user_agent=bool(raw.get("honest_user_agent", False)),
        verified=bool(raw.get("verified", False)),
    )


def load_endpoints(path: Path = ENDPOINTS_JSON) -> dict[str, Endpoint]:
    raw = _load_raw(path)
    return {slug: _endpoint_from(slug, e) for slug, e in raw["endpoints"].items()}


def load_audits(path: Path = ENDPOINTS_JSON) -> list[AuditGroup]:
    raw = _load_raw(path)
    groups = []
    for g in raw.get("audits", []):
        groups.append(AuditGroup(
            model_slug=g["model_slug"],
            reference=g["reference"],
            targets=tuple(AuditTarget(**t) for t in g["targets"]),
        ))
    return groups


ENDPOINTS: dict[str, Endpoint] = load_endpoints()


def get_endpoint(slug: str) -> Endpoint:
    """Resolve an endpoint by slug and verify its API key is loaded."""
    if slug not in ENDPOINTS:
        raise SystemExit(
            f"unknown endpoint {slug!r}; available: {sorted(ENDPOINTS)}"
        )
    ep = ENDPOINTS[slug]
    if ep.api_key() is None:
        raise SystemExit(
            f"{ep.api_key_env} not set in env (needed for {ep.label})"
        )
    return ep
