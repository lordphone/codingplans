"""planaudit command line.

planaudit catalog                       validate config, show key status
planaudit preflight [--endpoint SLUG]   one tiny call per endpoint with a key
planaudit audit --plan P [--tier T]     audit plan endpoints vs their references
planaudit collect PROBE --endpoint SLUG one probe on one endpoint -> var/runs/
planaudit compare PROBE REF TARGET      compare two saved runs (offline)
planaudit selftest                      offline end-to-end check against fake servers
planaudit export                        refresh data/catalog.json, data/audits/index.json
planaudit lab run|analyze|serve|proxy   calibration lab (see config/lab.toml)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from typing import Any

from . import catalog as catalog_mod
from . import probes as probe_registry
from .paths import load_env


def _kv(pairs: list[str]) -> dict[str, Any]:
    out = {}
    for p in pairs:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def cmd_catalog(a: argparse.Namespace) -> int:
    cat = catalog_mod.load()
    problems = cat.validate()
    for p in problems:
        print(f"problem: {p}")
    print(f"{len(cat.plans)} plans, {len(cat.endpoints)} endpoints, {len(cat.audits)} audits")
    for e in cat.endpoints.values():
        key = "key ok " if e.has_key else "no key "
        print(f"  {key} {e.role:8} {e.slug:24} {e.api_model:22} {e.base_url}")
    return 1 if problems else 0


def cmd_preflight(a: argparse.Namespace) -> int:
    from .client import ChatClient, Request

    cat = catalog_mod.load()
    slugs = a.endpoint or [s for s, e in cat.endpoints.items() if e.has_key]
    if not slugs:
        print("no endpoint has an API key set; see .env.example")
        return 1

    async def one(slug: str) -> None:
        ep = cat.endpoint(slug)
        req = Request(
            messages=[{"role": "user", "content": "Reply with the word OK."}],
            max_tokens=8,
            top_logprobs=3 if ep.logprobs else 0,
        )
        async with ChatClient(ep, min_interval_s=0) as c:
            r = await c.chat(req)
        if not r.ok:
            print(f"FAIL {slug}: {r.error}")
            return
        print(
            f"ok   {slug}: served_model={r.served_model} text={r.text.strip()[:20]!r} "
            f"usage={'yes' if r.prompt_tokens is not None else 'NO'} "
            f"cached_field={'yes' if r.cached_tokens is not None else 'no'} "
            f"logprobs={'yes' if r.logprobs else 'no'} ttft={r.ttft_s or 0:.2f}s"
        )

    async def main() -> None:
        for s in slugs:  # sequential: these are someone's paid accounts
            await one(s)

    asyncio.run(main())
    return 0


def cmd_audit(a: argparse.Namespace) -> int:
    from .audit import missing_keys, publish, run_audit
    from .export import export

    cat = catalog_mod.load()
    audits = [
        x for x in cat.audits if (a.all or x.plan in (a.plan or []) or x.target in (a.target or []))
    ]
    if not audits:
        print("nothing selected; use --plan, --target or --all")
        return 2
    for x in audits:
        missing = missing_keys(cat, x)
        tier = probe_registry.TIERS[a.tier]
        if a.dry_run or missing:
            state = f"missing {', '.join(missing)}" if missing else "ready"
            print(f"{x.plan}: {x.target} vs {x.reference} [{state}] probes={list(tier)}")
            continue
        result = asyncio.run(run_audit(cat, x, a.tier, calibrate=a.calibrate))
        path = publish(result)
        print(f"{x.plan}/{x.target}: {result['status']} -> {path}")
    if not a.dry_run:
        export(cat)
    return 0


def _endpoint_from_args(a: argparse.Namespace):
    if a.base_url:
        return catalog_mod.Endpoint(
            slug=a.endpoint or "adhoc",
            role="lab",
            base_url=a.base_url,
            api_model=a.model or "default",
            api_key_env=a.api_key_env,
            logprobs=a.logprobs,
            thinking_off={},
            max_concurrency=a.concurrency,
            min_interval_s=0,
        )
    ep = catalog_mod.load().endpoint(a.endpoint)
    return replace(ep, max_concurrency=a.concurrency) if a.concurrency else ep


def cmd_collect(a: argparse.Namespace) -> int:
    from .runner import collect

    probe = probe_registry.make(a.probe, **_kv(a.set))
    ep = _endpoint_from_args(a)
    (run,) = asyncio.run(collect(probe, [ep], labels=[a.label or ep.slug]))
    path = run.save()
    print(f"{path}  ({run.error_rate:.1%} errors)")
    print(json.dumps(probe.summarize(run), indent=1, default=float))
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    from .artifacts import Run

    ref, tgt = Run.load(a.reference), Run.load(a.target)
    probe = probe_registry.make(a.probe, **ref.config)
    v = probe.compare(ref, tgt)
    print(json.dumps(v.to_dict(), indent=1, default=float))
    print(f"\n{'FLAGGED' if v.flagged() else 'not flagged'}: {v.effect_name} = {v.effect:.4f} "
          f"(margin {v.margin}), p = {v.p_value:.4g}")  # fmt: skip
    return 1 if v.flagged() else 0


def cmd_selftest(a: argparse.Namespace) -> int:
    from .catalog import Endpoint
    from .fake import Behaviour, make_app
    from .runner import collect
    from .serve import background

    cases = {
        "logprob": ({"n_items": 40}, {"noise": 0.8}),
        "distribution": ({"n_items": 12, "samples": 24}, {"noise": 1.5}),
        "arithmetic": ({"n_items": 120}, {"wrong_rate": 0.3}),
        "needle": ({"lengths": [500, 6000], "per_length": 8}, {"context_cap": 1500}),
        "cache": ({"n_items": 8, "prefix_tokens": 4000}, {"prefix_cache": False}),
        "accounting": ({"n_items": 8}, {"inject_tokens": 40}),
    }
    ok = True
    for name, (cfg, bad) in cases.items():
        honest = {"prefill_s_per_1k": 0.03}
        with (
            background(make_app(Behaviour(**honest))) as u1,
            background(make_app(Behaviour(**honest))) as u2,
            background(make_app(Behaviour(**honest, **bad))) as u3,
        ):
            eps = [
                Endpoint(slug=s, role="lab", base_url=u, api_model="fake-model", logprobs=True,
                         thinking_off={}, max_concurrency=16, min_interval_s=0)
                for s, u in (("ref", u1), ("twin", u2), ("degraded", u3))
            ]  # fmt: skip
            probe = probe_registry.make(name, **cfg)
            ref, twin, deg = asyncio.run(collect(probe, eps, quiet=True))
            v_h, v_d = probe.compare(ref, twin, B=500), probe.compare(ref, deg, B=500)
        good = not v_h.flagged() and v_d.flagged()
        ok &= good
        print(
            f"{'PASS' if good else 'FAIL'} {name:13} honest effect={v_h.effect:+.3f} p={v_h.p_value:.3f}"
            f" | degraded effect={v_d.effect:+.3f} p={v_d.p_value:.3g}"
        )
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


def cmd_export(a: argparse.Namespace) -> int:
    from .export import export

    for f in export(catalog_mod.load()):
        print(f"wrote data/{f}")
    return 0


def cmd_lab(a: argparse.Namespace) -> int:
    from .lab import config as lab_config

    lab = lab_config.load()
    if a.lab_cmd == "run":
        from .lab.experiment import run_family

        fams = [lab.family(f) for f in a.family] if a.family else list(lab.families)
        for fam in fams:
            run_family(lab, fam, only=a.variant or None)
        return 0
    if a.lab_cmd == "analyze":
        from .lab.analysis import analyze

        done = analyze(lab, a.family or None, subsamples=a.subsamples, workers=a.workers)
        print("wrote " + ", ".join(f"data/lab/{f}.json" for f in done))
        return 0
    if a.lab_cmd == "report":
        from .paths import DATA

        doc = json.loads((DATA / "lab" / f"{a.family_id}.json").read_text())
        names = list(doc["probes"])
        print(f"{doc['name']}  (vLLM {doc['engine']['vllm']}, {doc['engine']['gpu']})")
        print("requests for 95% detection; '!' = false alarm, 'x' = flagged, '.' = not flagged\n")
        print(f"{'variant':16}" + "".join(f"{n[:11]:>12}" for n in names))
        by = {(r["variant"], r["probe"]): r for r in doc["results"]}
        for v in doc["variants"]:
            if v["id"] == doc["reference"]:
                continue
            cells = []
            for n in names:
                r = by.get((v["id"], n))
                if r is None or r["inconclusive"]:
                    cells.append("-")
                elif v["kind"] == "honest":
                    cells.append("!" if r["flagged"] else ".")
                elif r["requests_for_95"]:
                    cells.append(str(r["requests_for_95"]))
                else:
                    cells.append("x" if r["flagged"] else ".")
            print(f"{v['id']:16}" + "".join(f"{c:>12}" for c in cells))
        return 0
    if a.lab_cmd == "serve":
        import time

        from .lab.server import VllmServer

        fam = lab.family(a.family_id)
        with VllmServer(lab, fam.variant(a.variant_id), log_name=f"serve_{a.variant_id}") as s:
            print(f"serving {a.variant_id} at {s.base_url} (Ctrl-C to stop)")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
        return 0
    if a.lab_cmd == "proxy":
        import uvicorn

        from .lab.proxy import Cuts, make_app

        cuts = Cuts(
            truncate_tokens=a.truncate_tokens,
            inject_system=a.inject_system,
            phantom_cache=a.phantom_cache,
            clamp_max_tokens=a.clamp_max_tokens,
            delay_s=a.delay_s,
        )
        uvicorn.run(make_app(a.upstream, cuts), host="127.0.0.1", port=a.port)
        return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="planaudit", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("catalog", help="validate config and show endpoint key status")
    s = sub.add_parser("preflight", help="one tiny request per endpoint with a key")
    s.add_argument("--endpoint", action="append")

    s = sub.add_parser("audit", help="audit plans against their official APIs")
    s.add_argument("--plan", action="append")
    s.add_argument("--target", action="append")
    s.add_argument("--all", action="store_true")
    s.add_argument("--tier", choices=list(probe_registry.TIERS), default="quick")
    s.add_argument(
        "--calibrate",
        action="store_true",
        help="also sample the reference twice and widen margins by its self-difference",
    )
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("collect", help="run one probe against one endpoint")
    s.add_argument("probe", choices=list(probe_registry.PROBES))
    s.add_argument("--endpoint")
    s.add_argument("--base-url", help="ad-hoc OpenAI-compatible endpoint instead of a catalog slug")
    s.add_argument("--model")
    s.add_argument("--api-key-env")
    s.add_argument("--logprobs", action="store_true")
    s.add_argument("--concurrency", type=int, default=0)
    s.add_argument("--label")
    s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")

    s = sub.add_parser("compare", help="compare two saved runs")
    s.add_argument("probe", choices=list(probe_registry.PROBES))
    s.add_argument("reference")
    s.add_argument("target")

    sub.add_parser("selftest", help="offline check against fake servers")
    sub.add_parser("export", help="refresh data/ for the website")

    lab = sub.add_parser("lab", help="calibration lab")
    ls = lab.add_subparsers(dest="lab_cmd", required=True)
    s = ls.add_parser("run")
    s.add_argument("--family", action="append")
    s.add_argument("--variant", action="append")
    s = ls.add_parser("analyze")
    s.add_argument("--family", action="append")
    s.add_argument("--subsamples", type=int, default=100)
    s.add_argument("--workers", type=int, default=8)
    s = ls.add_parser("report", help="print a family's analysis as a table")
    s.add_argument("family_id")
    s = ls.add_parser("serve")
    s.add_argument("family_id")
    s.add_argument("variant_id")
    s = ls.add_parser("proxy")
    s.add_argument("--upstream", required=True)
    s.add_argument("--port", type=int, default=8200)
    s.add_argument("--truncate-tokens", type=int)
    s.add_argument("--inject-system")
    s.add_argument("--phantom-cache", action="store_true")
    s.add_argument("--clamp-max-tokens", type=int)
    s.add_argument("--delay-s", type=float, default=0.0)
    return p


COMMANDS = {
    "catalog": cmd_catalog,
    "preflight": cmd_preflight,
    "audit": cmd_audit,
    "collect": cmd_collect,
    "compare": cmd_compare,
    "selftest": cmd_selftest,
    "export": cmd_export,
    "lab": cmd_lab,
}


def main(argv: list[str] | None = None) -> int:
    load_env()
    a = build_parser().parse_args(argv)
    return COMMANDS[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
