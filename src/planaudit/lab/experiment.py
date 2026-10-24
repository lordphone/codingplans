"""Collect every probe on every variant of a lab family (resumable).

Runs land in var/runs/lab/<family>/<variant>/<probe>.json.gz. A run is
reused if its panel hash still matches the configured probe, so re-running
`planaudit lab run` only fills in what is missing or stale.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from .. import probes as probe_registry
from ..artifacts import Run
from ..catalog import Endpoint
from ..paths import RUNS
from ..runner import collect
from ..serve import background
from .config import Family, Lab, Variant
from .proxy import Cuts, make_app
from .server import VllmServer, gpu_name

LAB_RUNS = RUNS / "lab"


def run_path(family: str, variant: str, probe: str) -> Path:
    return LAB_RUNS / family / variant / f"{probe}.json.gz"


def load_run(family: str, variant: str, probe: str) -> Run | None:
    p = run_path(family, variant, probe)
    return Run.load(p) if p.exists() else None


def _missing(lab: Lab, fam: Family, v: Variant) -> list[str]:
    out = []
    for name, cfg in lab.probes_for(fam).items():
        probe = probe_registry.make(name, **cfg)
        r = load_run(fam.id, v.id, name)
        if r is None or r.panel_hash != probe.panel_hash():
            out.append(name)
    return out


def _endpoint(url: str, lab: Lab, v: Variant) -> Endpoint:
    return Endpoint(
        slug=f"lab-{v.id}", role="lab", base_url=url, api_model=lab.engine["served_model_name"],
        logprobs=True, thinking_off={}, max_concurrency=64, min_interval_s=0.0,
    )  # fmt: skip


async def _collect_variant(
    lab: Lab, fam: Family, v: Variant, url: str, todo: list[str], meta: dict
) -> None:
    ep = _endpoint(url, lab, v)
    for name in todo:
        probe = probe_registry.make(name, **lab.probes_for(fam)[name])
        print(f"[{fam.id}/{v.id}] {name} ({len(probe.items())} items)", file=sys.stderr, flush=True)
        (run,) = await collect(
            probe, [ep], labels=[f"lab:{fam.id}/{v.id}"], meta={**meta, "variant": v.id}, seed=0
        )
        if run.error_rate > 0.05:
            print(f"  warning: {run.error_rate:.0%} errors", file=sys.stderr)
        run.save(run_path(fam.id, v.id, name))


def run_family(lab: Lab, fam: Family, only: list[str] | None = None) -> None:
    variants = [v for v in fam.variants if only is None or v.id in only]
    # Group variants sharing a server so each model loads once.
    groups: dict[tuple, list[Variant]] = {}
    for v in variants:
        groups.setdefault(v.server_key, []).append(v)
    gpu = gpu_name()
    for key, vs in groups.items():
        todo = {v.id: _missing(lab, fam, v) for v in vs}
        if not any(todo.values()):
            print(f"[{fam.id}] {', '.join(v.id for v in vs)}: up to date", file=sys.stderr)
            continue
        server = VllmServer(lab, vs[0], log_name=f"{fam.id}_{vs[0].id}")
        print(f"[{fam.id}] starting vLLM: {key[0]} {' '.join(key[1])}", file=sys.stderr, flush=True)
        with server:
            meta = {
                "family": fam.id, "model": vs[0].model, "engine_args": list(server.command()[3:]),
                "vllm": server.version(), "gpu": gpu,
            }  # fmt: skip
            for v in vs:
                if not todo[v.id]:
                    continue
                if v.proxy:
                    with background(make_app(server.base_url[:-3], Cuts.from_dict(v.proxy))) as url:
                        asyncio.run(
                            _collect_variant(
                                lab, fam, v, url, todo[v.id], {**meta, "proxy": v.proxy}
                            )
                        )
                else:
                    asyncio.run(_collect_variant(lab, fam, v, server.base_url, todo[v.id], meta))
