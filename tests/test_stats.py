import numpy as np

from planaudit import stats


def test_signflip_null_and_alternative():
    g = np.random.default_rng(1)
    assert stats.signflip_test(g.normal(0, 1, 200), seed=1) > 0.05
    assert stats.signflip_test(g.normal(0.5, 1, 200), seed=1) < 0.001
    assert stats.signflip_test([0, 0, 0]) == 1.0
    assert stats.signflip_test([]) == 1.0


def test_signflip_is_calibrated():
    g = np.random.default_rng(2)
    ps = [stats.signflip_test(g.normal(0, 1, 30), B=500, seed=i) for i in range(300)]
    assert 0.02 < np.mean(np.array(ps) < 0.05) < 0.09


def test_wilson_bounds():
    lo, hi = stats.wilson(0, 10)
    assert lo == 0 and 0.2 < hi < 0.35
    assert stats.wilson(0, 0) == (0.0, 1.0)


def test_benjamini_hochberg_matches_reference():
    p = [0.01, 0.04, 0.03, 0.005]
    q = stats.benjamini_hochberg(p)
    # Reference values (statsmodels multipletests, method="fdr_bh").
    assert np.allclose(q, [0.02, 0.04, 0.04, 0.02])
    assert stats.benjamini_hochberg([]) == []


def test_perm_pvalue_never_zero():
    assert stats.perm_pvalue(10.0, np.zeros(99)) == 0.01
