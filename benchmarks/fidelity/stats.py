"""Small, dependency-free statistics helpers shared by the fidelity comparators.

Everything here is stdlib-only on purpose: comparators must stay pure,
fast, and runnable on a laptop without numpy/scipy. Each helper documents the
regime it is valid in; callers pick the right one for their sample sizes.

  * `two_proportion_test` — two-sided test for a gap in success rates
    (tool-call validity, unit-test pass rate, needle recall). Falls back to
    Fisher's exact test when any expected cell count is < 5.
  * `permutation_test_mean` — two-sided test for a gap in means of
    arbitrary per-sample scores (token counts, reasoning lengths). Exact
    enough with 10k resamples and makes no normality assumption.
  * `wilson_interval` — 95% CI for a binomial rate, honest at p≈0 or 1.
  * `benjamini_hochberg` — FDR-adjusted q-values across the tests of one
    audit (THREATS.md "multi-test correction").
"""

from __future__ import annotations

import math
import random
from statistics import fmean
from typing import Sequence

__all__ = [
    "benjamini_hochberg",
    "fisher_exact_two_sided",
    "norm_sf",
    "permutation_test_mean",
    "two_proportion_test",
    "wilson_interval",
]


def norm_sf(z: float) -> float:
    """Upper-tail probability of the standard normal, P(Z > z)."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. (0, 1) when n == 0."""
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _hypergeom_pmf(k: int, a_total: int, b_total: int, draws: int) -> float:
    return (
        math.comb(a_total, k) * math.comb(b_total, draws - k) / math.comb(a_total + b_total, draws)
    )


def fisher_exact_two_sided(x1: int, n1: int, x2: int, n2: int) -> float:
    """Two-sided Fisher exact p-value for the 2×2 table [[x1, n1-x1], [x2, n2-x2]].

    Sums the probabilities of every table with the same margins that is no
    more likely than the observed one (the standard "minimum-likelihood"
    two-sided definition, matching scipy.stats.fisher_exact)."""
    successes = x1 + x2
    lo = max(0, successes - n2)
    hi = min(n1, successes)
    p_obs = _hypergeom_pmf(x1, n1, n2, successes)
    total = 0.0
    for k in range(lo, hi + 1):
        pk = _hypergeom_pmf(k, n1, n2, successes)
        if pk <= p_obs * (1 + 1e-9):
            total += pk
    return min(1.0, total)


def two_proportion_test(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """Return (p1 - p2, two-sided p-value) for two binomial samples.

    Pooled z-test when every expected cell is ≥ 5, otherwise Fisher exact.
    Returns (0.0, 1.0) when either side has no samples — "no evidence" is
    never reported as a significant gap."""
    if n1 <= 0 or n2 <= 0:
        return 0.0, 1.0
    p1, p2 = x1 / n1, x2 / n2
    diff = p1 - p2
    pooled = (x1 + x2) / (n1 + n2)
    expected = (n1 * pooled, n1 * (1 - pooled), n2 * pooled, n2 * (1 - pooled))
    if min(expected) < 5:
        return diff, fisher_exact_two_sided(x1, n1, x2, n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0.0:
        return diff, 1.0
    return diff, min(1.0, 2.0 * norm_sf(abs(diff) / se))


def permutation_test_mean(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_resamples: int = 10_000,
    seed: int = 0,
) -> tuple[float, float]:
    """Return (mean(a) - mean(b), two-sided permutation p-value).

    The seed is fixed so a comparator stays a pure function of its inputs:
    re-running `compare.py` on the same artifacts gives the same p-value.
    Uses the (count + 1) / (n + 1) estimator so p is never exactly 0."""
    if not a or not b:
        return 0.0, 1.0
    observed = fmean(a) - fmean(b)
    pooled = list(a) + list(b)
    n_a = len(a)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_resamples):
        rng.shuffle(pooled)
        diff = fmean(pooled[:n_a]) - fmean(pooled[n_a:])
        if abs(diff) >= abs(observed) - 1e-12:
            extreme += 1
    return observed, (extreme + 1) / (n_resamples + 1)


def benjamini_hochberg(p_values: Sequence[float | None]) -> list[float | None]:
    """Benjamini–Hochberg FDR q-values. `None` entries pass through as None
    and do not count toward the number of hypotheses."""
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None]
    m = len(indexed)
    out: list[float | None] = [None] * len(p_values)
    if m == 0:
        return out
    indexed.sort(key=lambda t: t[1])
    running = 1.0
    for rank in range(m, 0, -1):
        i, p = indexed[rank - 1]
        running = min(running, p * m / rank)
        out[i] = min(1.0, running)
    return out
