"""Send a probe's panel to one or more endpoints and store the raw completions.

When several endpoints are given (an audit's reference and target), their
requests are interleaved in one shuffled schedule, so both sides are sampled
in the same wall-clock window and time-of-day or load effects hit both
equally (contemporaneous paired sampling). Each endpoint still gets its own
`Run`, so a reference run can be reused for other comparisons.
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from typing import Any

from .artifacts import Run, utc_now
from .catalog import Endpoint
from .client import ChatClient, Completion
from .probes.base import Item, Probe


async def _run_item(client: ChatClient, item: Item) -> list[Completion]:
    if item.sequential:
        return [await client.chat(r) for r in item.requests]
    return list(await asyncio.gather(*(client.chat(r) for r in item.requests)))


async def collect(
    probe: Probe,
    endpoints: list[Endpoint],
    *,
    labels: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    concurrency: int | None = None,
    min_interval_s: float | None = None,
    seed: int | None = None,
    quiet: bool = False,
) -> list[Run]:
    labels = labels or [e.slug for e in endpoints]
    for e in endpoints:
        if reason := probe.unusable(e):
            raise ValueError(f"{probe.name} cannot run on {e.slug}: {reason}")
    items = probe.items()
    panel = probe.panel_hash()
    limit = concurrency
    if probe.max_concurrency is not None:
        limit = min(limit or probe.max_concurrency, probe.max_concurrency)
    clients = [
        ChatClient(e, max_concurrency=limit, min_interval_s=min_interval_s) for e in endpoints
    ]
    results: list[dict[str, list[dict[str, Any]]]] = [{} for _ in endpoints]
    schedule = [(k, it) for k in range(len(endpoints)) for it in items]
    random.Random(seed).shuffle(schedule)
    started = utc_now()
    t0 = time.monotonic()
    done = 0
    # Bound in-flight items too, so a long panel doesn't open thousands of tasks.
    gate = asyncio.Semaphore(max(4, 4 * (limit or max(e.max_concurrency for e in endpoints))))

    async def one(k: int, it: Item) -> None:
        nonlocal done
        async with gate:
            rows = await _run_item(clients[k], it)
        dicts = []
        for c in rows:
            d = c.to_dict()
            if c.ok and (s := await asyncio.to_thread(probe.score, it, c)) is not None:
                d["score"] = s
            dicts.append(d)
        results[k][it.id] = dicts
        done += 1
        if not quiet and (done % max(1, len(schedule) // 20) == 0 or done == len(schedule)):
            rate = done / max(1e-9, time.monotonic() - t0)
            print(
                f"  {probe.name}: {done}/{len(schedule)} items ({rate:.1f}/s)",
                file=sys.stderr,
                flush=True,
            )

    try:
        await asyncio.gather(*(one(k, it) for k, it in schedule))
    finally:
        for c in clients:
            await c.aclose()
    finished = utc_now()
    item_meta = {it.id: it.meta for it in items if it.meta}
    return [
        Run(
            probe=probe.name,
            probe_version=probe.version,
            panel_hash=panel,
            label=labels[k],
            endpoint=e.public(),
            config=dict(probe.cfg),
            items=results[k],
            item_meta=item_meta,
            meta=dict(meta or {}),
            started_at=started,
            finished_at=finished,
        )
        for k, e in enumerate(endpoints)
    ]
