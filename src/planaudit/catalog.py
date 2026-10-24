"""Load config/catalog.toml into typed records.

The catalog is the single source of truth for providers, models, plans,
endpoints and audit pairings. `planaudit export` turns it into
data/catalog.json for the website.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

from .paths import CONFIG

Role = Literal["official", "plan", "lab"]


@dataclass(frozen=True)
class Endpoint:
    slug: str
    role: Role
    base_url: str
    api_model: str
    api_key_env: str | None = None
    provider: str | None = None
    model: str | None = None
    # Request params that turn reasoning off. None = cannot be disabled, so the
    # probes that need greedy, non-thinking output are skipped.
    thinking_off: dict[str, Any] | None = None
    logprobs: bool = False
    extra_params: dict[str, Any] = field(default_factory=dict)
    user_agent: str | None = None
    max_concurrency: int = 2
    min_interval_s: float = 0.5  # pacing between request starts
    verified: bool = False

    @property
    def env_prefix(self) -> str:
        return "PLANAUDIT_" + self.slug.upper().replace("-", "_").replace(".", "_")

    @property
    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env) or None

    @property
    def has_key(self) -> bool:
        return self.api_key_env is None or self.api_key is not None

    @property
    def can_disable_thinking(self) -> bool:
        return self.thinking_off is not None

    def resolved(self) -> Endpoint:
        """Apply PLANAUDIT_<SLUG>_BASE_URL / _MODEL overrides from the environment."""
        base = os.environ.get(f"{self.env_prefix}_BASE_URL", self.base_url)
        model = os.environ.get(f"{self.env_prefix}_MODEL", self.api_model)
        if base == self.base_url and model == self.api_model:
            return self
        return Endpoint(**{**asdict(self), "base_url": base, "api_model": model})

    def public(self) -> dict[str, Any]:
        """Metadata safe to publish (no key names beyond the env var, no secrets)."""
        return {
            "slug": self.slug,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "api_model": self.api_model,
            "base_url": self.base_url,
        }


@dataclass(frozen=True)
class Audit:
    plan: str
    target: str
    reference: str


@dataclass(frozen=True)
class Catalog:
    snapshot: str
    providers: list[dict[str, Any]]
    models: list[dict[str, Any]]
    plans: list[dict[str, Any]]
    endpoints: dict[str, Endpoint]
    audits: list[Audit]

    def endpoint(self, slug: str) -> Endpoint:
        try:
            return self.endpoints[slug].resolved()
        except KeyError:
            known = ", ".join(sorted(self.endpoints))
            raise KeyError(f"unknown endpoint {slug!r}; known: {known}") from None

    def plan(self, slug: str) -> dict[str, Any]:
        for p in self.plans:
            if p["slug"] == slug:
                return p
        raise KeyError(f"unknown plan {slug!r}")

    def validate(self) -> list[str]:
        """Return a list of consistency problems (empty = OK)."""
        problems: list[str] = []
        providers = {p["slug"] for p in self.providers}
        models = {m["slug"] for m in self.models}
        plans = {p["slug"]: p for p in self.plans}
        for p in self.plans:
            if p["provider"] not in providers:
                problems.append(f"plan {p['slug']}: unknown provider {p['provider']}")
            problems += [
                f"plan {p['slug']}: unknown model {m}"
                for m in p.get("models", [])
                if m not in models
            ]
        for e in self.endpoints.values():
            if e.provider and e.provider not in providers:
                problems.append(f"endpoint {e.slug}: unknown provider {e.provider}")
            if e.model and e.model not in models:
                problems.append(f"endpoint {e.slug}: unknown model {e.model}")
        for a in self.audits:
            if a.plan not in plans:
                problems.append(f"audit {a.target}: unknown plan {a.plan}")
            for slug, role in ((a.target, "plan"), (a.reference, "official")):
                e = self.endpoints.get(slug)
                if e is None:
                    problems.append(f"audit {a.plan}: unknown endpoint {slug}")
                elif e.role != role:
                    problems.append(f"audit {a.plan}: {slug} should have role {role}")
            t, r = self.endpoints.get(a.target), self.endpoints.get(a.reference)
            if t and r and t.model != r.model:
                problems.append(
                    f"audit {a.plan}: {a.target} and {a.reference} serve different models"
                )
            if t and a.plan in plans and t.model not in plans[a.plan].get("models", []):
                problems.append(f"audit {a.plan}: plan does not list model {t.model}")
        return problems


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    known = Endpoint.__dataclass_fields__
    unknown = set(raw) - set(known)
    if unknown:
        raise ValueError(f"endpoint {raw.get('slug')}: unknown fields {sorted(unknown)}")
    return Endpoint(**raw)


def parse(raw: dict[str, Any]) -> Catalog:
    endpoints = {e["slug"]: _endpoint(e) for e in raw.get("endpoints", [])}
    return Catalog(
        snapshot=raw.get("snapshot", ""),
        providers=raw.get("providers", []),
        models=raw.get("models", []),
        plans=raw.get("plans", []),
        endpoints=endpoints,
        audits=[Audit(**a) for a in raw.get("audits", [])],
    )


@cache
def load(path: Path = CONFIG / "catalog.toml") -> Catalog:
    with open(path, "rb") as f:
        return parse(tomllib.load(f))
