"""Lab analysis on fake-server runs: margins from honest variants, cuts flagged."""

from __future__ import annotations

from conftest import run_probe
from planaudit import probes
from planaudit.lab import analysis, experiment
from planaudit.lab.config import Family, Lab, Variant


def test_analysis_calibrates_margin_and_flags_cut(fake_endpoint, tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "LAB_RUNS", tmp_path / "runs")
    variants = (
        Variant("ref", "honest", "reference", "m"),
        Variant("twin", "honest", "honest twin", "m"),
        Variant("twin2", "honest", "another twin", "m"),
        Variant("quant", "cut", "noisy weights", "m", cut="quantization"),
    )
    fam = Family("fake", "Fake", 1.0, "ref", variants, probes=("logprob",))
    lab = Lab(engine={}, probes={"logprob": {"n_items": 40}}, families=(fam,))
    behaviour = {"ref": {}, "twin": {}, "twin2": {}, "quant": {"noise": 0.8}}
    probe = probes.make("logprob", n_items=40)
    for v in variants:
        (run,) = run_probe(probe, fake_endpoint(v.id, **behaviour[v.id]))
        run.save(experiment.run_path(fam.id, v.id, "logprob"))

    doc = analysis.analyze_family(lab, fam, subsamples=10, B=200, workers=1)
    res = {r["variant"]: r for r in doc["results"]}
    assert not res["twin"]["flagged"] and not res["twin2"]["flagged"]
    assert res["quant"]["flagged"]
    assert res["quant"]["requests_for_95"] is not None
    rates = [c["rate"] for c in res["quant"]["curve"]]
    assert rates[-1] == 1.0 and rates[0] <= rates[-1]
    assert doc["probes"]["logprob"]["margin"] >= probes.PROBES["logprob"].default_margin
