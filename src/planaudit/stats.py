"""Statistics shared by the probes.

Conventions:
  * every test returns a two-sided p-value unless its name says otherwise;
  * permutation p-values use the (1 + hits) / (1 + B) estimator, which is
    never zero and stays valid at small B;
  * "no data" is never evidence: degenerate inputs return p = 1.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from scipy import stats as sps


def rng(seed: int | None = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def perm_pvalue(observed: float, null: np.ndarray) -> float:
    """Upper-tail permutation p-value of `observed` against null draws."""
    null = np.asarray(null)
    return float((1 + np.count_nonzero(null >= observed - 1e-12)) / (1 + null.size))


def signflip_test(diffs: Sequence[float], *, B: int = 10_000, seed: int = 0) -> float:
    """Two-sided paired test that the mean of `diffs` is zero (random sign flips)."""
    d = np.asarray(diffs, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0 or np.allclose(d, 0):
        return 1.0
    obs = abs(d.mean())
    signs = rng(seed).choice([-1.0, 1.0], size=(B, d.size))
    null = np.abs((signs * d).mean(axis=1))
    return perm_pvalue(obs, null)


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for a binomial rate."""
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def mannwhitney(a: Sequence[float], b: Sequence[float]) -> float:
    a = np.asarray([x for x in a if x is not None and np.isfinite(x)], dtype=float)
    b = np.asarray([x for x in b if x is not None and np.isfinite(x)], dtype=float)
    if a.size < 2 or b.size < 2:
        return 1.0
    return float(sps.mannwhitneyu(a, b, alternative="two-sided").pvalue)


def wilcoxon(diffs: Sequence[float]) -> float:
    d = np.asarray([x for x in diffs if x is not None and np.isfinite(x)], dtype=float)
    if d.size < 3 or np.allclose(d, 0):
        return 1.0
    return float(sps.wilcoxon(d).pvalue)


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[np.ndarray], float] = np.mean,
    *,
    B: int = 2000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return float("nan"), float("nan")
    idx = rng(seed).integers(0, v.size, size=(B, v.size))
    draws = np.array([stat(v[i]) for i in idx])
    lo, hi = np.quantile(draws, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    """BH-adjusted q-values, in the input order."""
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    if n == 0:
        return []
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out.tolist()


def total_variation(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)
