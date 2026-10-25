"""Audit pipeline end-to-end against fake servers (no keys, no network)."""

from __future__ import annotations

import asyncio

from planaudit import audit as audit_mod
from planaudit import probes
from planaudit.catalog import Audit, parse


def _catalog(ref_url: str, tgt_url: str):
    return parse(
        {
            "providers": [{"slug": "p", "name": "P", "url": "x"}],
            "models": [{"slug": "m", "name": "M", "maker": "p", "open_weights": True}],
            "plans": [
                {"slug": "plan", "provider": "p", "name": "Plan", "kind": "maker", "models": ["m"],
                 "tiers": [{"name": "T", "price": 1, "currency": "USD", "limits": "-"}]}
            ],
            "endpoints": [
                {"slug": "ref", "role": "official", "provider": "p", "model": "m",
                 "api_model": "fake-model", "base_url": ref_url, "thinking_off": {},
                 "logprobs": True, "max_concurrency": 8, "min_interval_s": 0},
                {"slug": "tgt", "role": "plan", "provider": "p", "model": "m",
                 "api_model": "fake-model", "base_url": tgt_url, "thinking_off": {},
                 "logprobs": True, "max_concurrency": 8, "min_interval_s": 0},
            ],
            "audits": [{"plan": "plan", "target": "tgt", "reference": "ref"}],
        }
    )  # fmt: skip


def test_audit_flags_degraded_plan_and_passes_honest(fake_endpoint, monkeypatch):
    monkeypatch.setitem(
        probes.TIERS,
        "test",
        {"accounting": {"n_items": 6}, "arithmetic": {"n_items": 80}, "logprob": {"n_items": 30}},
    )
    monkeypatch.setattr(audit_mod, "lab_margins", lambda: {})
    ref = fake_endpoint("ref")
    honest = fake_endpoint("honest")
    bad = fake_endpoint("bad", inject_tokens=50, wrong_rate=0.4)
    for tgt, expect in ((honest, "match"), (bad, "gap")):
        cat = _catalog(ref.base_url, tgt.base_url)
        assert cat.validate() == []
        res = asyncio.run(
            audit_mod.run_audit(cat, Audit("plan", "tgt", "ref"), "test", calibrate=True,
                                save_runs=False)
        )  # fmt: skip
        assert res["status"] == expect, res["verdicts"]
        assert all("q_value" in v for v in res["verdicts"])


def test_repo_catalog_is_consistent():
    from planaudit.catalog import load

    assert load().validate() == []
