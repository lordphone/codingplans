"""Run artifacts: the raw, self-describing output of one probe on one endpoint.

A run never knows whether it is the reference or the target; that is decided
only when two runs are compared. Runs are reusable: one official run can be
compared against every plan that serves the same model, as long as the probe
version and panel hash match.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import Completion
from .paths import RUNS

SCHEMA = 1


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe(label: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in label)


@dataclass
class Run:
    probe: str
    probe_version: int
    panel_hash: str
    label: str  # endpoint slug, or "lab:<variant>"
    endpoint: dict[str, Any]
    config: dict[str, Any]
    items: dict[str, list[dict[str, Any]]]  # item id -> completions in request order
    item_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    schema: int = SCHEMA

    def completions(self, item_id: str) -> list[Completion]:
        # Parsed lazily and memoised (not a dataclass field, so never saved):
        # the lab compares the same runs thousands of times.
        cache = self.__dict__.setdefault("_parsed", {})
        if item_id not in cache:
            cache[item_id] = [Completion.from_dict(d) for d in self.items.get(item_id, [])]
        return cache[item_id]

    def all_completions(self) -> list[Completion]:
        return [Completion.from_dict(d) for rows in self.items.values() for d in rows]

    @property
    def error_rate(self) -> float:
        rows = [d for v in self.items.values() for d in v]
        return sum(1 for d in rows if d.get("error")) / len(rows) if rows else 0.0

    def save(self, path: Path | None = None) -> Path:
        if path is None:
            stamp = (self.started_at or utc_now()).replace(":", "").replace("-", "")
            path = RUNS / self.probe / f"{stamp}_{safe(self.label)}.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(asdict(self), f, separators=(",", ":"))
        return path

    @classmethod
    def load(cls, path: Path | str) -> Run:
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("schema") != SCHEMA:
            raise ValueError(f"{path}: schema {d.get('schema')} != {SCHEMA}")
        return cls(**d)


class IncomparableRuns(ValueError):
    pass


def assert_comparable(a: Run, b: Run) -> None:
    """Refuse to compare runs of different probes, versions or panels."""
    for attr in ("probe", "probe_version", "panel_hash"):
        if getattr(a, attr) != getattr(b, attr):
            raise IncomparableRuns(
                f"{attr} differs: {getattr(a, attr)!r} ({a.label}) vs {getattr(b, attr)!r} ({b.label})"
            )


def latest_run(probe: str, label: str, root: Path = RUNS) -> Path | None:
    files = sorted((root / probe).glob(f"*_{safe(label)}.json.gz"))
    return files[-1] if files else None
