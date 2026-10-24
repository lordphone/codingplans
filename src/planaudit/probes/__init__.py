"""Probe registry and audit tiers."""

from __future__ import annotations

from typing import Any

from .accuracy import ArithmeticProbe, NeedleProbe
from .base import Item, Probe, Verdict
from .code import CodeProbe
from .distribution import DistributionProbe
from .logprob import LogprobProbe
from .service import AccountingProbe, CacheProbe, SpeedProbe

PROBES: dict[str, type[Probe]] = {
    p.name: p
    for p in (
        LogprobProbe,
        DistributionProbe,
        ArithmeticProbe,
        CodeProbe,
        NeedleProbe,
        CacheProbe,
        AccountingProbe,
        SpeedProbe,
    )
}

# Audit tiers: which probes run, with what panel sizes. `quick` is cheap enough
# to run daily against a plan's quota; `standard` is the full weekly battery.
TIERS: dict[str, dict[str, dict[str, Any]]] = {
    "quick": {
        "accounting": {"n_items": 12},
        "distribution": {"n_items": 20, "samples": 16},
        "arithmetic": {"n_items": 80},
        "cache": {"n_items": 10},
        "speed": {"n_items": 8},
    },
    "standard": {
        "accounting": {},
        "logprob": {},
        "distribution": {},
        "arithmetic": {},
        "code": {},
        "needle": {},
        "cache": {},
        "speed": {},
    },
}


def make(name: str, **cfg: Any) -> Probe:
    try:
        return PROBES[name](**cfg)
    except KeyError:
        raise KeyError(f"unknown probe {name!r}; known: {', '.join(PROBES)}") from None


__all__ = ["PROBES", "TIERS", "Item", "Probe", "Verdict", "make"]
