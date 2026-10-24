"""Service-level probes: prompt caching, token accounting, speed.

These measure what the plan *does* rather than what the model *knows*, so
they work on every endpoint, including ones that force reasoning on.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .. import stats
from ..artifacts import Run
from ..client import Request
from . import panels
from .base import Item, Probe, Verdict, ok_rows

# ------------------------------------------------------------------ caching


class CacheProbe(Probe):
    """Is prompt caching real, and is what the usage block reports true?

    Each item is a fresh long prefix (a per-run nonce up front keeps it out of
    any existing cache) sent twice in a row with different questions. A real
    prefix cache makes the second request's time-to-first-token much shorter.
    Per endpoint we get the median speedup and the share of prompt tokens the
    API *claims* were cached; comparing the two exposes "phantom" caching
    (reported, not real) and missing caching.

    Comparison effect = median log-speedup(reference) - median log-speedup(target)."""

    name = "cache"
    title = "Prompt caching"
    detects = "missing or phantom prompt caching"
    effect_name = "lost log speedup"
    default_margin = 0.25  # ~22% less speedup
    max_concurrency = 1  # concurrent prefills would distort TTFT
    defaults = {"n_items": 24, "prefix_tokens": 6000, "seed": 1}

    def items(self) -> list[Item]:
        c = self.cfg
        out = []
        for i in range(c["n_items"]):
            r = panels.rng(c["seed"], "cache", i)
            doc = f"Document {self.RUN_NONCE}-{i}.\n" + panels.filler(
                r, int(c["prefix_tokens"] / 1.33)
            )
            reqs = [
                Request(
                    messages=panels.user(f"{doc}\n\nQuestion: {q} Answer in one word."),
                    max_tokens=4,
                    temperature=0.0,
                )
                for q in ("What season is mentioned first?", "Is the document about a city?")
            ]
            out.append(Item(id=f"c{i:03d}", requests=reqs, sequential=True))
        return out

    def _pairs(self, run: Run, ids: list[str]) -> list[tuple[float, float, float | None]]:
        """Per item: (cold ttft, warm ttft, reported cached share of the warm request)."""
        out = []
        for i in ids:
            cs = run.completions(i)
            if len(cs) != 2 or not all(c.ok and c.ttft_s for c in cs):
                continue
            cold, warm = cs
            share = (
                warm.cached_tokens / warm.prompt_tokens
                if warm.cached_tokens is not None and warm.prompt_tokens
                else None
            )
            out.append((cold.ttft_s, warm.ttft_s, share))
        return out

    def summarize(self, run: Run, ids: list[str] | None = None) -> dict[str, Any]:
        ids = self._ids(run, None, ids)
        pairs = self._pairs(run, ids)
        if not pairs:
            return {**super().summarize(run, ids), "n": 0}
        logs = np.log([c / w for c, w, _ in pairs])
        shares = [s for *_, s in pairs if s is not None]
        speedup = float(np.exp(np.median(logs)))
        reported = float(np.mean(shares)) if shares else None
        p_real = stats.wilcoxon(logs)
        real = speedup > 1.25 and p_real < 0.05
        if reported is None:
            status = "real (unreported)" if real else "none (unreported)"
        elif reported > 0.2:
            status = "real" if real else "phantom"
        else:
            status = "real (unreported)" if real else "none"
        return {
            **super().summarize(run, ids),
            "n": len(pairs),
            "median_speedup": speedup,
            "p_speedup": p_real,
            "reported_cached_share": reported,
            "cold_ttft_s": float(np.median([c for c, _, _ in pairs])),
            "warm_ttft_s": float(np.median([w for _, w, _ in pairs])),
            "status": status,
        }

    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict:
        a, b = self._pairs(ref, ids), self._pairs(tgt, ids)
        if len(a) < 5 or len(b) < 5:
            return self._empty("fewer than 5 cold/warm pairs on a side")
        la = np.log([c / w for c, w, _ in a])
        lb = np.log([c / w for c, w, _ in b])
        rs, ts = self.summarize(ref, ids), self.summarize(tgt, ids)
        return self.verdict(
            float(np.median(la) - np.median(lb)),
            stats.mannwhitney(la, lb),
            min(len(a), len(b)),
            detail={"phantom": ts["status"] == "phantom"},
            reference=rs,
            target=ts,
        )


# --------------------------------------------------------------- accounting


class AccountingProbe(Probe):
    """Do both endpoints count the same prompt tokens for the same request?

    Same model means same tokenizer and chat template, so reported
    `prompt_tokens` should agree exactly. A constant surplus on the plan side
    is a hidden system prompt (or rewritten prompt); a different slope against
    prompt length means a different tokenizer, i.e. a different model."""

    name = "accounting"
    title = "Token accounting"
    detects = "hidden prompt injection, tokenizer (model) swap"
    effect_name = "extra prompt tokens"
    default_margin = 3.0
    defaults = {"n_items": 24, "seed": 1}

    def items(self) -> list[Item]:
        c = self.cfg
        out = []
        for i in range(c["n_items"]):
            r = panels.rng(c["seed"], "acct", i)
            n_words = 20 + 60 * i
            req = Request(
                messages=panels.user(panels.filler(r, n_words) + "\n\nReply with OK."),
                max_tokens=2,
                temperature=0.0,
            )
            out.append(Item(id=f"t{i:03d}", requests=[req], meta={"words": n_words}))
        return out

    def _tokens(self, run: Run, ids: list[str]) -> dict[str, int]:
        out = {}
        for i in ids:
            rows = [c.prompt_tokens for c in ok_rows(run, i) if c.prompt_tokens is not None]
            if rows:
                out[i] = rows[0]
        return out

    def summarize(self, run: Run, ids: list[str] | None = None) -> dict[str, Any]:
        ids = self._ids(run, None, ids)
        toks = self._tokens(run, ids)
        base = {**super().summarize(run, ids), "usage_reported": len(toks) / max(1, len(ids))}
        if len(toks) >= 3:
            x = np.array([run.item_meta[i]["words"] for i in toks])
            y = np.array(list(toks.values()))
            slope, intercept = np.polyfit(x, y, 1)
            base |= {"tokens_per_word": float(slope), "intercept": float(intercept)}
        return base

    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict:
        a, b = self._tokens(ref, ids), self._tokens(tgt, ids)
        common = sorted(set(a) & set(b))
        if len(common) < 3:
            return self._empty("usage not reported on enough requests")
        d = np.array([b[i] - a[i] for i in common], dtype=float)
        x = np.array([ref.item_meta[i]["words"] for i in common], dtype=float)
        slope = float(np.polyfit(x, d, 1)[0]) if len(common) >= 3 else 0.0
        # Mean, matching the sign-flip test: a surplus on only some requests
        # still counts.
        return self.verdict(
            float(np.mean(d)),
            stats.signflip_test(d, B=B, seed=seed),
            len(common),
            detail={"diff_min": float(d.min()), "diff_max": float(d.max()), "diff_slope": slope},
            reference=self.summarize(ref, ids),
            target=self.summarize(tgt, ids),
        )


# --------------------------------------------------------------------- speed


class SpeedProbe(Probe):
    """Fixed workload, one request at a time: TTFT and single-stream decode speed.

    Same prompts and `max_tokens` on both sides so the numbers are comparable.
    This is per-request latency, not serving throughput."""

    name = "speed"
    title = "Speed"
    detects = "throttling, slower serving"
    effect_name = "decode slowdown"
    default_margin = 0.25
    max_concurrency = 1
    defaults = {"n_items": 16, "max_tokens": 256, "seed": 1}

    def items(self) -> list[Item]:
        out = []
        for i in range(self.cfg["n_items"]):
            topic = panels.TOPICS[i % len(panels.TOPICS)]
            req = Request(
                messages=panels.user(f"Write a detailed, multi-paragraph explanation of {topic}."),
                max_tokens=self.cfg["max_tokens"],
                temperature=0.0,
            )
            out.append(Item(id=f"s{i:03d}", requests=[req]))
        return out

    def _metric(self, run: Run, ids: list[str], attr: str) -> list[float]:
        vals = [getattr(c, attr) for i in ids for c in ok_rows(run, i)]
        return [v for v in vals if v]

    def summarize(self, run: Run, ids: list[str] | None = None) -> dict[str, Any]:
        ids = self._ids(run, None, ids)
        tps, ttft = self._metric(run, ids, "decode_tps"), self._metric(run, ids, "ttft_s")
        q = lambda v, p: float(np.percentile(v, p)) if v else None  # noqa: E731
        return {
            **super().summarize(run, ids),
            "decode_tps_p50": q(tps, 50),
            "decode_tps_p10": q(tps, 10),
            "ttft_p50_s": q(ttft, 50),
            "ttft_p90_s": q(ttft, 90),
        }

    def _compare(self, ref: Run, tgt: Run, ids: list[str], *, B: int, seed: int) -> Verdict:
        a, b = self._metric(ref, ids, "decode_tps"), self._metric(tgt, ids, "decode_tps")
        if len(a) < 3 or len(b) < 3:
            return self._empty("too few timed completions")
        return self.verdict(
            1 - float(np.median(b) / np.median(a)),
            stats.mannwhitney(a, b),
            min(len(a), len(b)),
            reference=self.summarize(ref, ids),
            target=self.summarize(tgt, ids),
        )
