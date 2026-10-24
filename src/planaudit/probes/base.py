"""The probe contract.

A probe is one detector. It has three parts, kept separate on purpose:

  1. `items()`   — a deterministic panel of requests (same config -> same
                   panel -> same `panel_hash`), so runs taken days apart on
                   different endpoints are comparable.
  2. collection  — done by `planaudit.runner`, which only sends requests and
                   stores raw completions. Probes never do I/O.
  3. `compare()` — a pure function of two runs (and optionally a subset of
                   item ids, which is how the lab measures power vs. budget).

`compare` returns a `Verdict` with an effect size and a p-value. Whether a
verdict is *flagged* depends on both: significance alone is not enough,
because two honest deployments on different hardware are never bit-identical
and enough queries will always find *some* difference. The effect must also
exceed a margin calibrated in the lab against honest serving variations.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

from ..artifacts import Run, assert_comparable
from ..catalog import Endpoint
from ..client import Completion, Request


@dataclass
class Item:
    id: str
    requests: list[Request]
    sequential: bool = False  # True: send in order, each after the previous finished
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Verdict:
    probe: str
    effect: float  # signed so that larger = target further from reference
    p_value: float
    n_items: int
    effect_name: str
    detail: dict[str, Any] = field(default_factory=dict)
    reference: dict[str, Any] = field(default_factory=dict)  # single-run summaries
    target: dict[str, Any] = field(default_factory=dict)
    inconclusive: str | None = None  # reason, when the data cannot support a verdict
    margin: float | None = None
    q_value: float | None = None

    def flagged(self, alpha: float = 0.05, margin: float | None = None) -> bool:
        if self.inconclusive:
            return False
        m = self.margin if margin is None else margin
        p = self.p_value if self.q_value is None else self.q_value
        return p < alpha and (m is None or self.effect > m)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Probe(ABC):
    name: ClassVar[str]
    version: ClassVar[int] = 1
    title: ClassVar[str]
    detects: ClassVar[str]  # the corner-cut this probe is designed for
    effect_name: ClassVar[str]
    defaults: ClassVar[dict[str, Any]] = {}
    default_margin: ClassVar[float | None] = None
    requires_logprobs: ClassVar[bool] = False
    requires_thinking_off: ClassVar[bool] = False
    # Timing-sensitive probes run with less concurrency than the endpoint allows.
    max_concurrency: ClassVar[int | None] = None
    # Probes whose prompts must be new to the server on every run (e.g. so a
    # cache probe's "cold" request is really cold) put RUN_NONCE in their
    # messages; the runner replaces it with a fresh value per run. The panel
    # hash is computed on the placeholder, so runs stay comparable.
    RUN_NONCE: ClassVar[str] = "{{run_nonce}}"

    def __init__(self, **cfg: Any):
        unknown = set(cfg) - set(self.defaults)
        if unknown:
            raise ValueError(f"{self.name}: unknown config {sorted(unknown)}")
        self.cfg: dict[str, Any] = {**self.defaults, **cfg}

    # ------------------------------------------------------------ panel

    @abstractmethod
    def items(self) -> list[Item]: ...

    def panel_hash(self) -> str:
        h = hashlib.sha256()
        h.update(f"{self.name}:{self.version}".encode())
        for it in self.items():
            h.update(it.id.encode())
            for r in it.requests:
                h.update(json.dumps(asdict(r), sort_keys=True).encode())
        return h.hexdigest()[:16]

    def score(self, item: Item, completion: Completion) -> dict[str, Any] | None:
        """Optional per-completion grading, run at collection time and stored
        on the completion under "score". Keeps `compare` pure even when grading
        is expensive or has side effects (e.g. executing generated code)."""
        return None

    def unusable(self, endpoint: Endpoint) -> str | None:
        """Reason this probe cannot run on `endpoint`, or None."""
        if self.requires_logprobs and not endpoint.logprobs:
            return "endpoint does not return logprobs"
        if self.requires_thinking_off and not endpoint.can_disable_thinking:
            return "reasoning cannot be disabled on this endpoint"
        return None

    # ----------------------------------------------------------- compare

    def summarize(self, run: Run, ids: list[str] | None = None) -> dict[str, Any]:
        """Single-run summary for reports. Override for probe-specific numbers."""
        rows = [c for i in self._ids(run, None, ids) for c in run.completions(i)]
        return {"requests": len(rows), "error_rate": _err(rows)}

    @abstractmethod
    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict: ...

    def compare(
        self, ref: Run, tgt: Run, ids: list[str] | None = None, *, B: int = 2000, seed: int = 0
    ) -> Verdict:
        assert_comparable(ref, tgt)
        use = self._ids(ref, tgt, ids)
        if not use:
            return self._empty("no items in common")
        v = self._compare(ref, tgt, use, B=B, seed=seed)
        if v.margin is None:
            v.margin = self.default_margin
        return v

    # ----------------------------------------------------------- helpers

    def _ids(self, a: Run, b: Run | None, ids: list[str] | None) -> list[str]:
        keys = set(a.items) if b is None else set(a.items) & set(b.items)
        if ids is not None:
            keys &= set(ids)
        return sorted(keys)

    def _empty(self, reason: str) -> Verdict:
        return Verdict(
            probe=self.name,
            effect=0.0,
            p_value=1.0,
            n_items=0,
            effect_name=self.effect_name,
            inconclusive=reason,
            margin=self.default_margin,
        )

    def verdict(self, effect: float, p: float, n: int, **kw: Any) -> Verdict:
        return Verdict(
            probe=self.name,
            effect=float(effect),
            p_value=float(p),
            n_items=n,
            effect_name=self.effect_name,
            **kw,
        )


def _err(rows: list[Completion]) -> float:
    return sum(1 for c in rows if not c.ok) / len(rows) if rows else 0.0


def ok_rows(run: Run, item_id: str) -> list[Completion]:
    return [c for c in run.completions(item_id) if c.ok]
