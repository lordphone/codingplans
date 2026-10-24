"""Next-token distribution shift, from returned top-k logprobs.

Detects: weight quantization, model substitution.

Each prompt is sent twice per endpoint at temperature 0 with `top_logprobs`.
For every generated position where both completions share the same greedy
prefix (so the conditioning context is identical) we compare the two top-k
next-token distributions by total variation. Per prompt:

    excess = mean TV(reference, target) - mean TV(within each endpoint)

The within-endpoint term absorbs batch nondeterminism. Under the null
(same distribution) the four completions of a prompt are exchangeable, so
the p-value comes from re-pairing them (3 partitions per prompt).
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np

from ..artifacts import Run
from ..client import Completion, Request
from . import panels
from .base import Item, Probe, Verdict, ok_rows

TEMPLATES = [
    "Write one sentence about {topic}.",
    "Give a short, creative title for an essay about {topic}.",
    "In one line, what is the most surprising fact about {topic}?",
    "Describe {topic} to a child in one sentence.",
    "Start a short poem about {topic}. One line only.",
    "Name three words you associate with {topic}.",
    "Write a tweet-length opinion on {topic}.",
    "Explain why {topic} matter, in one sentence.",
    "Suggest a name for a startup working on {topic}.",
    "Write the opening line of a mystery novel involving {topic}.",
]


def _dist(pos: list[Any]) -> dict[str, float]:
    """Top-k alternatives at one position as a probability dict."""
    alts = pos[2] or [[pos[0], pos[1]]]
    return {tok: math.exp(lp) for tok, lp in alts}


def tv_logprobs(a: Completion, b: Completion) -> float | None:
    """Mean TV over positions where the greedy prefixes agree."""
    if not a.logprobs or not b.logprobs:
        return None
    tvs = []
    for pa, pb in zip(a.logprobs, b.logprobs, strict=False):
        da, db = _dist(pa), _dist(pb)
        keys = set(da) | set(db)
        tvs.append(0.5 * sum(abs(da.get(k, 0.0) - db.get(k, 0.0)) for k in keys))
        if pa[0] != pb[0]:  # contexts diverge after this position
            break
    return float(np.mean(tvs)) if tvs else None


# The three ways to split 4 completions [a1, a2, b1, b2] into two pairs, as
# (within-pairs, cross-pairs) over the 6 pairwise distances indexed below.
_PAIRS = list(combinations(range(4), 2))  # (0,1) (0,2) (0,3) (1,2) (1,3) (2,3)
_PARTITIONS = []
for g in ([(0, 1), (2, 3)], [(0, 2), (1, 3)], [(0, 3), (1, 2)]):
    within = [_PAIRS.index(p) for p in g]
    _PARTITIONS.append((within, [i for i in range(6) if i not in within]))


class LogprobProbe(Probe):
    name = "logprob"
    title = "Next-token distribution"
    detects = "quantization, model swap"
    effect_name = "excess total variation"
    requires_logprobs = True
    requires_thinking_off = True
    default_margin = 0.02
    defaults = {"n_items": 200, "positions": 6, "top_k": 5, "seed": 1}

    def items(self) -> list[Item]:
        c = self.cfg
        out = []
        for i in range(c["n_items"]):
            r = panels.rng(c["seed"], "logprob", i)
            prompt = r.choice(TEMPLATES).format(topic=r.choice(panels.TOPICS))
            req = Request(
                messages=panels.user(prompt),
                max_tokens=c["positions"],
                temperature=0.0,
                top_logprobs=c["top_k"],
            )
            # Sequential, so the two replicas land in different server batches and
            # the within-endpoint term sees the same batch nondeterminism as the
            # cross-endpoint one.
            out.append(Item(id=f"lp{i:04d}", requests=[req, req], sequential=True))
        return out

    def _distances(self, ref: Run, tgt: Run, ids: list[str]) -> np.ndarray:
        """(n_items, 6) pairwise TV matrix; NaN rows where data is missing."""
        memo = self.__dict__.setdefault("_memo", {})
        D = np.full((len(ids), 6), np.nan)
        for row, i in enumerate(ids):
            key = (id(ref), id(tgt), i)
            if key not in memo:
                a, b = ok_rows(ref, i)[:2], ok_rows(tgt, i)[:2]
                ds = None
                if len(a) == 2 and len(b) == 2:
                    cs = a + b
                    ds = [tv_logprobs(cs[x], cs[y]) for x, y in _PAIRS]
                    ds = ds if all(d is not None for d in ds) else None
                memo[key] = ds
            if memo[key] is not None:
                D[row] = memo[key]
        return D[~np.isnan(D).any(axis=1)]

    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict:
        D = self._distances(ref, tgt, ids)
        if len(D) < 5:
            return self._empty("fewer than 5 prompts with logprobs on both sides")
        excess = np.stack(
            [D[:, cross].mean(1) - D[:, within].mean(1) for within, cross in _PARTITIONS], axis=1
        )  # (n, 3): column 0 is the observed labelling
        obs = excess[:, 0].mean()
        pick = np.random.default_rng(seed).integers(0, 3, size=(B, len(D)))
        null = excess[np.arange(len(D)), pick].mean(axis=1)
        p = float((1 + np.count_nonzero(null >= obs - 1e-12)) / (1 + B))
        return self.verdict(
            obs,
            p,
            len(D),
            detail={
                "cross_tv": float(D[:, [1, 2, 3, 4]].mean()),
                "within_ref_tv": float(D[:, 0].mean()),
                "within_target_tv": float(D[:, 5].mean()),
            },
        )
