"""Endpoint registry for fidelity audits.

Each `Endpoint` is a single OpenAI-compatible chat target. The fidelity tests
take **one** endpoint at a time (see `benchmarks/fidelity/weights/`), so this
file is a flat registry — no notion of "pair." Comparison is a separate step
that joins two run artifacts.

Adding a new endpoint:
  1. Define an `Endpoint` with a stable filename-safe slug.
  2. Pick a stable `api_key_env` name; document it in `.env.example`.
  3. Register in `ENDPOINTS` under the slug.

Convention: `<model-short>-<provider-slug>`, e.g. `glm5-official`,
`glm5-alibaba`. Reference (vendor) endpoints get `-official`; everything else
takes the provider's slug.

All base URLs and api_key_env names can be overridden per-environment via
`<SLUG>_BASE_URL` etc. — useful when a vendor moves hosts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Endpoint",
    "ENDPOINTS",
    "get_endpoint",
]


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is not None and v.strip():
        return v.strip()
    return None


@dataclass(frozen=True)
class Endpoint:
    """One OpenAI-compatible chat endpoint.

    `label` is a short human-readable id used in artifact filenames and
    summary metadata. `extra_params` is merged into every request body sent
    to this endpoint — use it for per-vendor flags like disabling thinking
    mode so two endpoints compare apples-to-apples at the same temperature.
    """

    label: str
    base_url: str
    api_key_env: str
    model: str
    extra_params: dict[str, Any] = field(default_factory=dict)

    def api_key(self) -> str | None:
        return _env(self.api_key_env)


# ---------------------------------------------------------------------------
# Built-in endpoints
# ---------------------------------------------------------------------------
#
# v1 ships GLM-5 on Alibaba Cloud Model Studio coding plan plus the official
# z.ai API as the reference. Add more plans (kimi-k2.5-*, qwen3-coder-plus-*,
# etc.) by appending entries — no test code changes required.

ENDPOINTS: dict[str, Endpoint] = {
    "glm5-official": Endpoint(
        label="glm5-official",
        base_url=_env("GLM5_OFFICIAL_BASE_URL") or "https://api.z.ai/api/paas/v4",
        api_key_env="ZAI_API_KEY",
        model=_env("GLM5_OFFICIAL_MODEL") or "glm-5",
    ),
    "glm5-alibaba": Endpoint(
        label="glm5-alibaba",
        base_url=_env("GLM5_ALIBABA_BASE_URL")
        or "https://coding-intl.dashscope.aliyuncs.com/v1",
        api_key_env="ALIBABA_CLOUD_MODEL_STUDIO_CODING_PLAN_API_KEY",
        model=_env("GLM5_ALIBABA_MODEL") or "glm-5",
    ),
}


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
