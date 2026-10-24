"""Paired accuracy probes: the same graded tasks on both endpoints.

Every item is graded at collection time (`score` -> {"correct": 0..1}). The
comparison is paired by item: effect = reference accuracy - target accuracy
(positive = the target is worse), p from a sign-flip test on per-item
differences, which is exact for paired data and needs no normality.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .. import stats
from ..artifacts import Run
from ..client import Completion, Request
from . import panels
from .base import Item, Probe, Verdict, ok_rows


class AccuracyProbe(Probe):
    effect_name = "accuracy drop"
    requires_thinking_off = True
    group_key: str | None = None  # item_meta key to break accuracy down by

    def item_scores(self, run: Run, ids: list[str]) -> np.ndarray:
        out = []
        for i in ids:
            rows = [c.score["correct"] for c in ok_rows(run, i) if c.score]
            out.append(float(np.mean(rows)) if rows else np.nan)
        return np.asarray(out)

    def summarize(self, run: Run, ids: list[str] | None = None) -> dict[str, Any]:
        ids = self._ids(run, None, ids)
        s = self.item_scores(run, ids)
        s = s[np.isfinite(s)]
        out = {**super().summarize(run, ids), "accuracy": float(s.mean()) if s.size else None}
        if self.group_key:
            groups: dict[str, list[float]] = {}
            for i, v in zip(ids, self.item_scores(run, ids), strict=True):
                if np.isfinite(v):
                    groups.setdefault(str(run.item_meta[i][self.group_key]), []).append(v)
            out["by_" + self.group_key] = {
                k: float(np.mean(v)) for k, v in sorted(groups.items(), key=lambda kv: float(kv[0]))
            }
        return out

    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict:
        a, b = self.item_scores(ref, ids), self.item_scores(tgt, ids)
        keep = np.isfinite(a) & np.isfinite(b)
        if keep.sum() < 5:
            return self._empty("fewer than 5 items graded on both sides")
        d = a[keep] - b[keep]
        lo, hi = stats.bootstrap_ci(d, B=min(B, 2000), seed=seed)
        return self.verdict(
            d.mean(),
            stats.signflip_test(d, B=B, seed=seed),
            int(keep.sum()),
            detail={"effect_ci": [lo, hi]},
            reference=self.summarize(ref, ids),
            target=self.summarize(tgt, ids),
        )


# ---------------------------------------------------------------- arithmetic

_INT = re.compile(r"-?\d[\d,]*")


def last_int(text: str) -> int | None:
    found = _INT.findall(text.replace(" ", "").replace(" ", ""))
    return int(found[-1].replace(",", "")) if found else None


class ArithmeticProbe(AccuracyProbe):
    """Multi-digit multiplication without chain of thought.

    Quantization damage concentrates in exact, multi-step execution (carries),
    while general benchmarks barely move, which makes this a cheap and
    sensitive quantization signal."""

    name = "arithmetic"
    title = "Mental arithmetic"
    detects = "quantization, model swap"
    default_margin = 0.03
    group_key = "digits"
    defaults = {"n_items": 240, "digits": [2, 3, 4, 5], "seed": 1}

    def items(self) -> list[Item]:
        c = self.cfg
        out = []
        for i in range(c["n_items"]):
            r = panels.rng(c["seed"], "arith", i)
            d = c["digits"][i % len(c["digits"])]
            a = r.randint(10 ** (d - 1), 10**d - 1)
            b = r.randint(10 ** (d - 1), 10**d - 1)
            req = Request(
                messages=panels.user(
                    f"What is {a} × {b}? Reply with only the final number, no working."
                ),
                max_tokens=24,
                temperature=0.0,
            )
            out.append(Item(id=f"a{i:04d}", requests=[req], meta={"answer": a * b, "digits": d}))
        return out

    def score(self, item: Item, completion: Completion) -> dict[str, Any]:
        return {"correct": float(last_int(completion.text) == item.meta["answer"])}


# -------------------------------------------------------------------- needle


class NeedleProbe(AccuracyProbe):
    """Retrieve one fact from pseudo-prose of growing length.

    A context cap or middle-out truncation shows as an accuracy cliff at a
    length the reference handles; KV-cache quantization as a gradual decline.
    Two distractor facts with the same shape make lexical shortcuts harder."""

    name = "needle"
    title = "Long-context recall"
    detects = "context truncation, KV-cache quantization"
    default_margin = 0.05
    group_key = "tokens"
    defaults = {"lengths": [1000, 4000, 8000, 16000, 24000], "per_length": 16, "seed": 1}

    def items(self) -> list[Item]:
        c = self.cfg
        out = []
        for L in c["lengths"]:
            for j in range(c["per_length"]):
                r = panels.rng(c["seed"], "needle", L, j)
                keys = r.sample([(col, ani) for col in panels.COLORS for ani in panels.ANIMALS], 3)
                codes = [r.randint(100000, 999999) for _ in keys]
                n_words = int(L / 1.33)
                words = panels.filler(r, n_words).split(" ")
                depths = sorted(r.random() for _ in keys)
                for (col, ani), code, depth in reversed(
                    list(zip(keys, codes, depths, strict=True))
                ):
                    pos = int(depth * len(words))
                    words.insert(pos, f"The access code for the {col} {ani} vault is {code}.")
                target = r.randrange(len(keys))
                col, ani = keys[target]
                prompt = (
                    "Read the document and answer the question at the end.\n\n<document>\n"
                    + " ".join(words)
                    + f"\n</document>\n\nWhat is the access code for the {col} {ani} vault? "
                    "Reply with only the six-digit code."
                )
                req = Request(messages=panels.user(prompt), max_tokens=16, temperature=0.0)
                out.append(
                    Item(
                        id=f"n{L:06d}_{j:02d}",
                        requests=[req],
                        meta={"answer": codes[target], "tokens": L, "depth": depths[target]},
                    )
                )
        return out

    def score(self, item: Item, completion: Completion) -> dict[str, Any]:
        return {"correct": float(str(item.meta["answer"]) in completion.text)}
