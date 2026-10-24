"""End-to-end: every probe passes an honest twin and flags a degraded one."""

from __future__ import annotations

import pytest

from conftest import run_probe
from planaudit import probes
from planaudit.artifacts import IncomparableRuns, Run


def _pair(fake_endpoint, probe, honest_kw, bad_kw):
    ref = fake_endpoint("ref", **honest_kw)
    twin = fake_endpoint("twin", **honest_kw)
    bad = fake_endpoint("bad", **bad_kw)
    r_ref, r_twin, r_bad = run_probe(probe, ref, twin, bad)
    return probe.compare(r_ref, r_twin, B=500), probe.compare(r_ref, r_bad, B=500)


CASES = [
    ("logprob", {"n_items": 40}, {}, {"noise": 0.8}),
    ("distribution", {"n_items": 12, "samples": 24}, {}, {"noise": 1.5}),
    ("arithmetic", {"n_items": 120}, {}, {"wrong_rate": 0.3}),
    ("needle", {"lengths": [500, 2000, 6000], "per_length": 8}, {}, {"context_cap": 1500}),
    (
        "cache",
        {"n_items": 8, "prefix_tokens": 4000},
        {"prefill_s_per_1k": 0.03},
        {"prefill_s_per_1k": 0.03, "prefix_cache": False},
    ),
    ("accounting", {"n_items": 8}, {}, {"inject_tokens": 40}),
]


@pytest.mark.parametrize(("name", "cfg", "honest", "bad"), CASES, ids=[c[0] for c in CASES])
def test_probe_separates_honest_from_degraded(fake_endpoint, name, cfg, honest, bad):
    probe = probes.make(name, **cfg)
    honest_v, bad_v = _pair(fake_endpoint, probe, honest, bad)
    assert not honest_v.inconclusive, honest_v.inconclusive
    assert not honest_v.flagged(), honest_v
    assert bad_v.flagged(), bad_v


def test_phantom_cache_is_reported(fake_endpoint):
    probe = probes.make("cache", n_items=6, prefix_tokens=4000)
    ep = fake_endpoint("phantom", prefix_cache=False, prefill_s_per_1k=0.03)
    # A server that claims cached tokens without being faster:
    ep_bad = fake_endpoint("liar", prefix_cache=False, prefill_s_per_1k=0.03)
    (run,) = run_probe(probe, ep)
    assert probe.summarize(run)["status"] in ("none", "none (unreported)")
    (run_bad,) = run_probe(probe, ep_bad)
    for rows in run_bad.items.values():
        rows[1]["cached_tokens"] = int(rows[1]["prompt_tokens"] * 0.9)
    assert probe.summarize(run_bad)["status"] == "phantom"


def test_panels_are_deterministic_and_versioned():
    a, b = probes.make("arithmetic", n_items=10), probes.make("arithmetic", n_items=10)
    assert a.panel_hash() == b.panel_hash()
    assert a.panel_hash() != probes.make("arithmetic", n_items=10, seed=2).panel_hash()


def test_incomparable_runs_are_refused(fake_endpoint, tmp_path):
    ep = fake_endpoint()
    (r1,) = run_probe(probes.make("accounting", n_items=4), ep)
    (r2,) = run_probe(probes.make("accounting", n_items=5), ep)
    with pytest.raises(IncomparableRuns):
        probes.make("accounting", n_items=4).compare(r1, r2)
    path = r1.save(tmp_path / "r.json.gz")
    assert Run.load(path).items == r1.items
