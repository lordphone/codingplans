"""Typed view of config/lab.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import CONFIG


@dataclass(frozen=True)
class Variant:
    id: str
    kind: str  # "honest" | "cut"
    label: str
    model: str
    args: tuple[str, ...] = ()
    cut: str | None = None
    proxy: dict[str, Any] = field(default_factory=dict)

    @property
    def server_key(self) -> tuple[str, tuple[str, ...]]:
        """Variants with the same key can share one running vLLM server."""
        return (self.model, self.args)


@dataclass(frozen=True)
class Family:
    id: str
    name: str
    params_b: float
    reference: str
    variants: tuple[Variant, ...]
    probes: tuple[str, ...] | None = None

    def variant(self, vid: str) -> Variant:
        for v in self.variants:
            if v.id == vid:
                return v
        raise KeyError(f"{self.id}: unknown variant {vid!r}")


@dataclass(frozen=True)
class Lab:
    engine: dict[str, Any]
    probes: dict[str, dict[str, Any]]
    families: tuple[Family, ...]

    @property
    def vllm(self) -> str:
        return os.path.expanduser(os.environ.get("PLANAUDIT_VLLM", self.engine["vllm"]))

    def family(self, fid: str) -> Family:
        for f in self.families:
            if f.id == fid:
                return f
        raise KeyError(f"unknown family {fid!r}; known: {[f.id for f in self.families]}")

    def probes_for(self, family: Family) -> dict[str, dict[str, Any]]:
        names = family.probes or tuple(self.probes)
        return {n: self.probes.get(n, {}) for n in names}


def load(path: Path = CONFIG / "lab.toml") -> Lab:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    families = []
    for fam in raw["families"]:
        variants = tuple(
            Variant(**{**v, "args": tuple(v.get("args", ()))}) for v in fam.pop("variants")
        )
        probes = fam.pop("probes", None)
        families.append(Family(**fam, variants=variants, probes=tuple(probes) if probes else None))
    return Lab(engine=raw["engine"], probes=raw.get("probes", {}), families=tuple(families))
