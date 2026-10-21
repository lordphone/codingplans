#!/usr/bin/env python3
"""Run a fidelity audit: every test in a tier, for every plan in an audit group,
against that group's official reference — then compare, correct, and report.

  python benchmarks/audit/run_audit.py --dry-run                 # show the plan, no calls
  python benchmarks/audit/run_audit.py --group glm-5 --tier quick
  python benchmarks/audit/run_audit.py --all --tier standard --ingest
  python benchmarks/audit/run_audit.py --group glm-5 --tier quick --calibrate   # official vs official

Per (group, test):
  1. Reference artifact: reuse the newest `<stamp>_<reference>_<test>.summary.json`
     younger than --reuse-days if one exists, else run the test on the
     reference endpoint. (One official run feeds every plan audit for that model.)
  2. Target artifact: run the test on each plan endpoint.
  3. Compare with the test's pure comparator. If the stored reference turns out
     to be incomparable (panel changed since), re-run the reference once.

Per target, all p-values from that audit are Benjamini–Hochberg adjusted. A test
is reported as `fail` only when its comparator says fail AND (it has no p-value,
i.e. a deterministic threshold, or its q-value < --fdr). A comparator fail that
does not survive FDR correction is reported `inconclusive`.

Writes `benchmarks/audit/reports/<stamp>_<target>.json` (local-only) and, with
--ingest, inserts rows into Supabase `audit_results` (needs SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY).

Exit code: 0 all pass/inconclusive, 1 any fail, 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_FIDELITY = _HERE.parent / "fidelity"
for _p in (_FIDELITY, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from framework import load_dotenv, read_run_result  # noqa: E402
from registry import TESTS, TIERS, TestSpec, headline  # noqa: E402
from stats import benjamini_hochberg  # noqa: E402
from targets import ENDPOINTS, AuditGroup, AuditTarget, load_audits  # noqa: E402

REPORTS_DIR = Path(os.environ.get("CODINGPLANS_REPORTS_DIR") or _HERE / "reports")


def _log(msg: str) -> None:
    print(f"[audit {datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _artifacts(spec: TestSpec, label: str) -> list[Path]:
    # Oldest first by write time (stamps can carry a collision suffix, which
    # would sort wrongly as strings).
    return sorted(spec.runs_dir.glob(f"*_{label}_{spec.name}.summary.json"),
                  key=lambda p: p.stat().st_mtime)


def _stamp_age_days(path: Path) -> float:
    stamp = path.name.split("_", 1)[0][:15] + "Z"  # drop any collision suffix
    try:
        t = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return float("inf")
    return (datetime.now(timezone.utc) - t).total_seconds() / 86400


def _run_test(spec: TestSpec, endpoint: str, tier: str, extra: list[str]) -> Path:
    """Run one test CLI against one endpoint; return the new summary path."""
    before = set(_artifacts(spec, endpoint))
    cmd = [sys.executable, str(spec.script), "--endpoint", endpoint,
           *spec.tier_args.get(tier, []), *extra]
    _log(f"run {spec.name} on {endpoint}: {' '.join(cmd[1:])}")
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(spec.script.parent))
    if proc.returncode != 0:
        raise RuntimeError(f"{spec.name} on {endpoint} exited {proc.returncode}")
    new = sorted(set(_artifacts(spec, endpoint)) - before)
    if not new:
        raise RuntimeError(f"{spec.name} on {endpoint} wrote no summary artifact")
    _log(f"done {spec.name} on {endpoint} in {time.monotonic() - started:.0f}s")
    return new[-1]


def _status(fail: bool, inconclusive: bool, q: float | None, fdr: float) -> tuple[str, str]:
    if inconclusive:
        return "inconclusive", "Too few usable samples on one side."
    if not fail:
        return "pass", ""
    if q is not None and q >= fdr:
        return "inconclusive", f"Comparator flagged a gap, but q={q:.3f} does not survive FDR correction."
    return "fail", ""


def audit_group(group: AuditGroup, tests: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    ref = ENDPOINTS[group.reference]
    targets = [t for t in group.targets if args.target in (None, t.endpoint)]
    if args.calibrate:
        # Official vs official: two fresh, independent runs of the reference.
        # Every test should pass; a fail here means the threshold is too tight.
        targets = [AuditTarget(endpoint=ref.label, provider_slug="(calibration)", plan_slug="(calibration)")]
    results: list[dict[str, Any]] = []
    rows_by_target: dict[str, list[dict[str, Any]]] = {t.endpoint: [] for t in targets}

    for name in tests:
        spec = TESTS[name]
        if spec.needs_thinking_off and ref.thinking_off is None and ref.thinking_on is not None:
            _log(f"skip {name} for {group.model_slug}: model cannot disable thinking")
            continue
        ref_path: Path | None = None
        reusable = [] if args.calibrate else [
            p for p in _artifacts(spec, ref.label) if _stamp_age_days(p) <= args.reuse_days
        ]
        if reusable:
            ref_path = reusable[-1]
            _log(f"reuse reference {ref_path.name}")

        for tgt in targets:
            row: dict[str, Any] = {
                "test_name": name, "family": spec.family,
                "model_slug": group.model_slug, "provider_slug": tgt.provider_slug,
                "plan_slug": tgt.plan_slug, "reference_label": ref.label,
                "target_label": tgt.endpoint,
            }
            try:
                if ref_path is None:
                    ref_path = _run_test(spec, ref.label, args.tier, args.extra)
                tgt_path = _run_test(spec, tgt.endpoint, args.tier, args.extra)
                from compare import COMPARATORS  # heavy import; deferred

                compare = COMPARATORS[name]
                reference, target = read_run_result(ref_path), read_run_result(tgt_path)
                try:
                    report = compare(reference, target)
                except ValueError:
                    _log(f"stored reference incomparable for {name}; re-running reference")
                    ref_path = _run_test(spec, ref.label, args.tier, args.extra)
                    reference = read_run_result(ref_path)
                    report = compare(reference, target)
                rep = asdict(report)
                h = headline(name, rep)
                row.update({
                    "metric": h.metric, "reference_value": h.reference_value,
                    "target_value": h.target_value, "p_value": h.p_value,
                    "comparator_fail": h.fail, "inconclusive": h.inconclusive,
                    "summary": h.summary, "panel_id": target.panel_id,
                    "reference_artifact": ref_path.name, "target_artifact": tgt_path.name,
                    "report": rep,
                })
            except Exception as e:  # noqa: BLE001 — one broken test must not kill the audit
                _log(f"ERROR {name} / {tgt.endpoint}: {e}")
                row.update({"status": "error", "summary": str(e)[:500], "metric": None,
                            "reference_value": None, "target_value": None, "p_value": None,
                            "report": {}})
            rows_by_target[tgt.endpoint].append(row)

    for endpoint, rows in rows_by_target.items():
        qs = benjamini_hochberg([r.get("p_value") for r in rows if r.get("status") != "error"])
        q_iter = iter(qs)
        for r in rows:
            if r.get("status") == "error":
                r["q_value"] = None
                continue
            r["q_value"] = next(q_iter)
            status, note = _status(r["comparator_fail"], r["inconclusive"], r["q_value"], args.fdr)
            r["status"] = status
            if note:
                r["summary"] = f"{r['summary']} {note}"
        results.extend(rows)
        _write_report(endpoint, group, rows)
    return results


def _write_report(endpoint: str, group: AuditGroup, rows: list[dict[str, Any]]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"{stamp}_{endpoint}.json"
    payload = {"stamp_utc": stamp, "model_slug": group.model_slug,
               "reference": group.reference, "target": endpoint, "results": rows}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _log(f"wrote {path}")
    for r in rows:
        _log(f"  {r['status']:<12} {r['test_name']:<20} {r['summary'][:110]}")


def _print_plan(groups: list[AuditGroup], tests: list[str], args: argparse.Namespace) -> None:
    for g in groups:
        ref = ENDPOINTS[g.reference]
        print(f"\n{g.model_slug}: reference {ref.label} ({ref.model} @ {ref.base_url}) "
              f"key {ref.api_key_env}={'set' if ref.api_key() else 'MISSING'}")
        for t in g.targets:
            if args.target not in (None, t.endpoint):
                continue
            ep = ENDPOINTS[t.endpoint]
            print(f"  target {ep.label} → {t.provider_slug}/{t.plan_slug} "
                  f"key {ep.api_key_env}={'set' if ep.api_key() else 'MISSING'}"
                  f"{'' if ep.verified else ' (unverified)'}")
        runnable = [n for n in tests
                    if not (TESTS[n].needs_thinking_off and ref.thinking_off is None and ref.thinking_on is not None)]
        print(f"  tests: {', '.join(runnable)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sel = parser.add_mutually_exclusive_group()
    sel.add_argument("--group", help="Audit group model_slug from endpoints.json")
    sel.add_argument("--all", action="store_true", help="Every audit group")
    parser.add_argument("--target", help="Only this plan endpoint slug")
    parser.add_argument("--tier", choices=sorted(TIERS), default="quick")
    parser.add_argument("--tests", help="Comma-separated test names (overrides --tier)")
    parser.add_argument("--reuse-days", type=float, default=7.0,
                        help="Reuse reference artifacts younger than this (default 7)")
    parser.add_argument("--fdr", type=float, default=0.05, help="BH false-discovery rate")
    parser.add_argument("--ingest", action="store_true", help="Insert results into Supabase")
    parser.add_argument("--calibrate", action="store_true",
                        help="Compare each reference against a fresh run of itself (threshold sanity check; never ingested)")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and exit")
    parser.add_argument("--extra", nargs=argparse.REMAINDER, default=[],
                        help="Extra args passed to every test CLI (e.g. --extra --panel-size 3 --n 1)")
    args = parser.parse_args()

    load_dotenv()
    groups = load_audits()
    if args.group:
        groups = [g for g in groups if g.model_slug == args.group]
        if not groups:
            print(f"unknown group {args.group!r}", file=sys.stderr)
            return 2
    elif not args.all and not args.dry_run:
        print("pass --group <model_slug>, --all, or --dry-run", file=sys.stderr)
        return 2

    tests = args.tests.split(",") if args.tests else TIERS[args.tier]
    unknown = [t for t in tests if t not in TESTS]
    if unknown:
        print(f"unknown tests: {unknown}", file=sys.stderr)
        return 2

    if args.dry_run:
        _print_plan(groups, tests, args)
        return 0

    all_rows: list[dict[str, Any]] = []
    for g in groups:
        missing = [ENDPOINTS[s].api_key_env for s in [g.reference, *(t.endpoint for t in g.targets)]
                   if ENDPOINTS[s].api_key() is None and (s == g.reference or args.target in (None, s))]
        if missing:
            _log(f"skip group {g.model_slug}: missing keys {sorted(set(missing))}")
            continue
        all_rows.extend(audit_group(g, tests, args))

    if args.ingest and all_rows and not args.calibrate:
        from ingest import ingest_audit_rows

        ingest_audit_rows(all_rows)
    return 1 if any(r["status"] == "fail" for r in all_rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
