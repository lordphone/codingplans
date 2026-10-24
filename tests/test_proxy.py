"""The adversary proxy applies each cut and the probes notice."""

from __future__ import annotations

from conftest import run_probe
from planaudit import probes
from planaudit.catalog import Endpoint
from planaudit.fake import Behaviour
from planaudit.fake import make_app as fake_app
from planaudit.lab.proxy import Cuts, make_app, truncate_middle
from planaudit.serve import background


def _via_proxy(cuts: Cuts, **behaviour):
    upstream = background(fake_app(Behaviour(**behaviour)))
    up = upstream.__enter__()
    proxy = background(make_app(up[: -len("/v1")], cuts))
    url = proxy.__enter__()
    ep = Endpoint(slug="proxied", role="lab", base_url=url, api_model="fake-model",
                  logprobs=True, thinking_off={}, max_concurrency=8, min_interval_s=0)  # fmt: skip
    return ep, (proxy, upstream)


def _close(ctx):
    for cm in ctx:
        cm.__exit__(None, None, None)


def test_truncate_middle_keeps_ends():
    msgs = [{"role": "user", "content": "HEAD " + "x" * 10_000 + " TAIL"}]
    out = truncate_middle(msgs, 500)
    text = out[0]["content"]
    assert text.startswith("HEAD") and text.endswith("TAIL") and len(text) < 2200


def test_injected_system_prompt_is_counted(fake_endpoint):
    probe = probes.make("accounting", n_items=6)
    ref = fake_endpoint("ref")
    ep, ctx = _via_proxy(Cuts(inject_system="You are a helpful assistant. " * 10))
    try:
        r_ref, r_tgt = run_probe(probe, ref, ep)
    finally:
        _close(ctx)
    v = probe.compare(r_ref, r_tgt, B=500)
    assert v.flagged() and v.effect > 30


def test_phantom_cache_reports_cached_tokens():
    probe = probes.make("cache", n_items=6, prefix_tokens=3000)
    ep, ctx = _via_proxy(Cuts(phantom_cache=True), prefix_cache=False, report_cache=False,
                         prefill_s_per_1k=0.02)  # fmt: skip
    try:
        (run,) = run_probe(probe, ep)
    finally:
        _close(ctx)
    assert probe.summarize(run)["status"] == "phantom"
