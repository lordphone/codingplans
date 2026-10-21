#!/usr/bin/env python3
"""Offline self-test for the benchmark suite. No API keys, no network.

  python benchmarks/selftest.py          # unit checks (fast)
  python benchmarks/selftest.py --e2e    # + full audit pipeline against a local fake API

Unit checks cover the statistics helpers against known values, the JSON-schema
validator, every new comparator on synthetic honest-vs-cheating artifacts
(each must pass the honest case and fail the cheating case), and every coding
task's hidden tests against its reference solution.

The e2e check starts a local OpenAI-compatible SSE server with two personas —
`honest` and `cheater` (hidden system prompt, broken tool-call JSON, ignored
max_tokens / stop, replayed answers, no reasoning) — points two endpoints at it
via <SLUG>_BASE_URL overrides, and runs `audit/run_audit.py` end-to-end on a
trimmed panel. The cheater must fail the integrity/agentic tests; honest vs
honest must not.
"""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FID = ROOT / "fidelity"
for p in [FID, *(FID / f for f in ("agentic", "integrity", "reasoning", "coding", "long_context")), ROOT / "audit"]:
    sys.path.insert(0, str(p))

from framework import PromptItem, PromptOutcome, RunResult, SCHEMA_VERSION, panel_hash  # noqa: E402
import stats  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILURES.append(msg)


def fake_run(test: str, label: str, panel: list[PromptItem], records: list[list[dict]],
             completions: list[list[str]] | None = None, n: int = 1) -> RunResult:
    return RunResult(
        schema_version=SCHEMA_VERSION, test_name=test, panel_id="x", panel_size=len(panel),
        prompt_hash=panel_hash(panel), n_samples=n, max_tokens=1, schedule_seed=0,
        sleep_range_s=[0, 0], stamp_utc="20260101T000000Z", endpoint_label=label,
        endpoint_model="m", endpoint_base_url="u", endpoint_extra_params={}, user_agent="",
        prompts=[PromptOutcome(i, it.name, dict(it.meta or {}),
                               completions=(completions[i] if completions else [""] * len(records[i])),
                               records=records[i]) for i, it in enumerate(panel)],
    )


# ---------------------------------------------------------------------------
# Unit checks
# ---------------------------------------------------------------------------


def test_stats() -> None:
    print("stats")
    # scipy.stats.fisher_exact([[8, 2], [1, 5]]) -> p = 0.034965...
    check(abs(stats.fisher_exact_two_sided(8, 10, 1, 6) - 0.03496503) < 1e-6, "fisher exact matches scipy")
    d, p = stats.two_proportion_test(90, 100, 70, 100)
    check(abs(d - 0.2) < 1e-9 and 0.0003 < p < 0.0006, f"two-proportion z (p={p:.5f})")
    check(stats.two_proportion_test(0, 0, 3, 5) == (0.0, 1.0), "empty side → no evidence")
    q = stats.benjamini_hochberg([0.01, 0.04, 0.03, None, 0.5])
    check([round(x, 4) if x is not None else None for x in q] == [0.04, 0.0533, 0.0533, None, 0.5], f"BH {q}")
    lo, hi = stats.wilson_interval(0, 10)
    check(lo == 0.0 and 0.27 < hi < 0.29, "wilson at p=0")
    _, p = stats.permutation_test_mean([1.0] * 30, [2.0] * 30, n_resamples=2000)
    check(p < 0.01, "permutation test detects a clear shift")
    r1, r2 = random.Random(1), random.Random(2)
    _, p = stats.permutation_test_mean([r1.random() for _ in range(40)],
                                       [r2.random() for _ in range(40)], n_resamples=2000)
    check(p > 0.05, f"permutation test calm on same distribution (p={p:.3f})")


def test_schema_and_tool_calls() -> None:
    print("tool_calls")
    from schema_lite import validate
    from test_tool_calls import TEST_NAME, check_calls, compare_tool_calls
    from tool_prompts import TOOL_CALLS_PROMPTS, TOOL_SCHEMAS

    s = TOOL_SCHEMAS["run_command"]
    check(validate({"command": "ls"}, s) == [], "valid args")
    check(validate({"command": "ls", "timeout_s": 0}, s) != [], "minimum enforced")
    check(validate({"cmd": "ls"}, s) != [], "missing required + extra prop")
    check(validate({"command": "ls", "timeout_s": True}, s) != [], "bool is not integer")

    good = check_calls([{"name": "run_command", "arguments": '{"command":"pytest"}'}],
                       {"expect": "tool", "allowed": ["run_command"], "min_calls": 1})
    check(good["schema_valid"] and good["decision_ok"], "check_calls good call")
    bad = check_calls([{"name": "run_command", "arguments": '{"command": pytest'}],
                      {"expect": "tool", "allowed": ["run_command"], "min_calls": 1})
    check(not bad["schema_valid"] and bad["schema_problems"], "check_calls broken JSON")

    panel = TOOL_CALLS_PROMPTS
    def recs(valid: bool, follow: bool) -> list[list[dict]]:
        out = []
        for it in panel:
            m = it.meta or {}
            trig = (m["expect"] == "tool") if follow else (m["expect"] != "tool")
            out.append([{"triggered": trig, "schema_valid": trig and valid, "decision_ok": follow,
                         "schema_problems": [] if valid else ["x"]}] * 4)
        return out
    ref = fake_run(TEST_NAME, "ref", panel, recs(True, True), n=4)
    honest = compare_tool_calls(ref, fake_run(TEST_NAME, "tgt", panel, recs(True, True), n=4))
    check(not honest.fail and honest.trigger_similarity == 1.0, "honest tool calls pass")
    broken = compare_tool_calls(ref, fake_run(TEST_NAME, "tgt", panel, recs(False, True), n=4))
    check(broken.fail and broken.target_schema_accuracy == 0.0, "broken tool JSON fails")
    flipped = compare_tool_calls(ref, fake_run(TEST_NAME, "tgt", panel, recs(True, False), n=4))
    check(flipped.fail and flipped.trigger_similarity == 0.0, "inverted trigger decisions fail")


def test_token_accounting() -> None:
    print("token_accounting")
    from integrity_prompts import TOKEN_ACCOUNTING_PROMPTS as panel
    from test_token_accounting import TEST_NAME, compare_token_accounting, linear_fit

    check(tuple(round(x, 6) for x in linear_fit([1, 2, 3], [12, 14, 16])) == (10.0, 2.0), "OLS fit")
    def recs(offset: int, slope: float) -> list[list[dict]]:
        return [[{"prompt_tokens": int((20 + it.meta["chars"] // 4) * slope) + offset,
                  "completion_tokens": 3, "visible_chars": 12}] * 3 for it in panel]
    ref = fake_run(TEST_NAME, "ref", panel, recs(0, 1.0), n=3)
    check(not compare_token_accounting(ref, fake_run(TEST_NAME, "t", panel, recs(4, 1.0), n=3)).fail,
          "small template difference passes")
    inj = compare_token_accounting(ref, fake_run(TEST_NAME, "t", panel, recs(900, 1.0), n=3))
    check(inj.fail and 850 < inj.intercept_tokens < 950, f"hidden 900-token prompt fails (intercept {inj.intercept_tokens})")
    infl = compare_token_accounting(ref, fake_run(TEST_NAME, "t", panel, recs(0, 1.2), n=3))
    check(infl.fail and infl.slope > 1.1, "20% inflation fails")
    none = [[{"prompt_tokens": None, "completion_tokens": None, "visible_chars": 12}] * 3 for _ in panel]
    check(compare_token_accounting(ref, fake_run(TEST_NAME, "t", panel, none, n=3)).inconclusive,
          "no usage reported → inconclusive")


def test_param_and_cache() -> None:
    print("param_compliance / response_cache")
    from client import ChatResponse
    from integrity_prompts import CACHE_PROMPTS, PARAM_PROMPTS
    from test_param_compliance import TEST_NAME as PT, check_probe, compare_param_compliance
    from test_response_cache import TEST_NAME as CT, compare_response_cache, nonce_outcome

    r = ChatResponse(content="x" * 40, completion_tokens=16, finish_reason="length", latency_s=1)
    check(check_probe({"probe": "max_tokens", "max_tokens": 16}, r) is True, "max_tokens honored")
    r2 = ChatResponse(content="x" * 400, completion_tokens=120, finish_reason="stop", latency_s=1)
    check(check_probe({"probe": "max_tokens", "max_tokens": 16}, r2) is False, "max_tokens ignored")
    check(check_probe({"probe": "stop", "forbidden": "17"}, ChatResponse("1, 2, 16, 17", 5, "stop", 1)) is False, "stop ignored")
    check(check_probe({"probe": "json_mode"}, ChatResponse('{"a": 1}', 5, "stop", 1)) is True, "json ok")
    big = "\n".join(str(i) for i in range(1, 2501))
    check(check_probe({"probe": "output_cap", "last": 2500}, ChatResponse(big, 9000, "stop", 1)) is True, "full output")
    check(check_probe({"probe": "output_cap", "last": 2500}, ChatResponse(big[:4000], 2000, "length", 1)) is False, "capped output")

    def precs(comply: bool, diverse: bool) -> list[list[dict]]:
        out = []
        for it in PARAM_PROMPTS:
            m = it.meta
            if m["probe"] == "temperature":
                hot = m["temperature"] > 0 and diverse
                out.append([{"probe": "temperature", "compliant": None,
                             "normalized": f"name{k if hot else 0}"} for k in range(8)])
            else:
                out.append([{"probe": m["probe"], "compliant": comply, "normalized": ""}] * 8)
        return out
    ref = fake_run(PT, "ref", PARAM_PROMPTS, precs(True, True), n=8)
    check(not compare_param_compliance(ref, fake_run(PT, "t", PARAM_PROMPTS, precs(True, True), n=8)).fail, "honest params pass")
    check(compare_param_compliance(ref, fake_run(PT, "t", PARAM_PROMPTS, precs(False, True), n=8)).fail, "ignored params fail")
    flat = compare_param_compliance(ref, fake_run(PT, "t", PARAM_PROMPTS, precs(True, False), n=8))
    check(flat.fail and flat.temperature_collapsed, "pinned temperature fails")

    check(nonce_outcome("OPS-AB12CD: flaky runner", "OPS-AB12CD") == "ok", "nonce ok")
    check(nonce_outcome("OPS-ZZZZZZ: flaky runner", "OPS-AB12CD") == "stale", "nonce stale")
    def crecs(cached: bool) -> list[list[dict]]:
        out = []
        for it in CACHE_PROMPTS:
            if it.meta["probe"] == "entropy":
                out.append([{"probe": "entropy", "normalized": "same" if cached else f"v{k}"} for k in range(8)])
            else:
                out.append([{"probe": "nonce", "normalized": "", "nonce_outcome": "stale" if cached else "ok"}] * 8)
        return out
    ref = fake_run(CT, "ref", CACHE_PROMPTS, crecs(False), n=8)
    check(not compare_response_cache(ref, fake_run(CT, "t", CACHE_PROMPTS, crecs(False), n=8)).fail, "fresh answers pass")
    check(compare_response_cache(ref, fake_run(CT, "t", CACHE_PROMPTS, crecs(True), n=8)).fail, "replayed answers fail")


def test_reasoning_and_code() -> None:
    print("reasoning_budget / code_exec")
    from coding_tasks import CODE_PROMPTS
    from reasoning_prompts import REASONING_PROMPTS
    from reference_solutions import REFERENCE_SOLUTIONS
    from sandbox import extract_code, run_tests
    from test_code_exec import TEST_NAME as XT, compare_code_exec
    from test_reasoning_budget import TEST_NAME as RT, compare_reasoning_budget, parse_answer

    check(parse_answer("so...\nANSWER: 1,234") == 1234, "parse ANSWER")
    check(len({p.name for p in REASONING_PROMPTS}) == len(REASONING_PROMPTS) == 24, "24 unique reasoning prompts")
    rng = random.Random(0)
    def rrecs(tokens: int, acc: float, think: bool = True) -> list[list[dict]]:
        return [[{"correct": rng.random() < acc, "has_reasoning": think,
                  "reasoning_tokens": int(tokens * rng.uniform(0.7, 1.3)) if think else 0,
                  "reasoning_chars": 0, "finish_reason": "stop"} for _ in range(2)] for _ in REASONING_PROMPTS]
    ref = fake_run(RT, "ref", REASONING_PROMPTS, rrecs(3000, 0.85), n=2)
    check(not compare_reasoning_budget(ref, fake_run(RT, "t", REASONING_PROMPTS, rrecs(3000, 0.85), n=2)).fail, "same budget passes")
    cut = compare_reasoning_budget(ref, fake_run(RT, "t", REASONING_PROMPTS, rrecs(900, 0.8), n=2))
    check(cut.fail and cut.reasoning_ratio_target_over_ref < 0.5, "budget cut to 30% fails")
    check(compare_reasoning_budget(ref, fake_run(RT, "t", REASONING_PROMPTS, rrecs(0, 0.5, False), n=2)).fail, "thinking disabled fails")

    check(extract_code("text\n```python\nx = 1\n```\nmore") == "x = 1\n", "extract fenced code")
    all_ok = all(run_tests(REFERENCE_SOLUTIONS[p.name], p.meta["tests"]).passed for p in CODE_PROMPTS)
    check(all_ok, f"all {len(CODE_PROMPTS)} reference solutions pass their hidden tests")
    check(run_tests("while True: pass", "", timeout_s=2).outcome == "timeout", "sandbox timeout")
    check(run_tests("import os\nassert 'ZAI_API_KEY' not in os.environ", "").passed, "sandbox env scrubbed")
    def xrecs(rate: float) -> list[list[dict]]:
        return [[{"passed": k < round(rate * 3), "outcome": "pass" if k < round(rate * 3) else "assertion"}
                 for k in range(3)] for _ in CODE_PROMPTS]
    ref = fake_run(XT, "ref", CODE_PROMPTS, xrecs(1.0), n=3)
    check(not compare_code_exec(ref, fake_run(XT, "t", CODE_PROMPTS, xrecs(1.0), n=3)).fail, "equal pass rate passes")
    bad = compare_code_exec(ref, fake_run(XT, "t", CODE_PROMPTS, xrecs(1 / 3), n=3))
    check(bad.fail and len(bad.regressions) == len(CODE_PROMPTS), "pass-rate collapse fails")


def test_registry() -> None:
    print("registry / endpoints")
    import compare
    from registry import TESTS, TIERS
    from targets import ENDPOINTS, load_audits

    check(set(TESTS) == set(compare.COMPARATORS), "every registered test has a comparator")
    check(all(s.script.exists() for s in TESTS.values()), "every test script exists")
    check(all(set(t) <= set(TESTS) for t in TIERS.values()), "tiers reference known tests")
    for g in load_audits():
        check(g.reference in ENDPOINTS and ENDPOINTS[g.reference].role == "official",
              f"{g.model_slug}: reference is an official endpoint")
        for t in g.targets:
            check(t.endpoint in ENDPOINTS and ENDPOINTS[t.endpoint].role == "plan",
                  f"{g.model_slug}: {t.endpoint} is a plan endpoint")
    seed = (ROOT.parent / "supabase" / "seed.sql").read_text()
    for g in load_audits():
        check(f"'{g.model_slug}'" in seed, f"seed.sql has model {g.model_slug}")
        for t in g.targets:
            check(f"'{t.plan_slug}'" in seed and f"'{t.provider_slug}'" in seed,
                  f"seed.sql has {t.provider_slug}/{t.plan_slug}")


# ---------------------------------------------------------------------------
# End-to-end against a fake OpenAI-compatible server
# ---------------------------------------------------------------------------


class FakeAPI(BaseHTTPRequestHandler):
    """POST /<persona>/v1/chat/completions, persona ∈ {honest, cheater}."""

    cache: dict[str, str] = {}

    def log_message(self, *a) -> None:  # silence
        pass

    def _sse(self, chunks: list[dict]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in chunks:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def do_POST(self) -> None:
        persona = self.path.strip("/").split("/")[0]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cheat = persona == "cheater"
        msgs = body["messages"]
        user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        prompt_chars = sum(len(m.get("content") or "") for m in msgs)
        prompt_tokens = 10 + prompt_chars // 4 + (700 if cheat else 0)
        max_tokens = body.get("max_tokens", 256)
        temp = body.get("temperature", 0)
        rng = random.Random()
        reasoning = "" if cheat or body.get("thinking", {}).get("type") == "disabled" else "Let me think. " * 40

        tool_calls = None
        if body.get("tools") and ("Run" in user or "run" in user or "Open" in user or "Search" in user
                                  or "Find" in user or "fix" in user or "verify" in user):
            args = '{"command": "pytest -q"' if cheat else '{"command": "pytest -q"}'
            tool_calls = [{"index": 0, "id": "c1", "function": {"name": "run_command", "arguments": args}}]
        if "Ticket OPS-" in user:
            nonce = user.split("Ticket ")[1].split(":")[0]
            text = (FakeAPI.cache.setdefault("nonce", nonce) if cheat else nonce) + ": the runner is out of memory."
        elif "integers from 1 to 2500" in user:
            text = "\n".join(str(i) for i in range(1, (900 if cheat else 2501)))
        elif "JSON object" in user:
            text = '{"name": "x", "stars": 1, "topics": []}'
        elif "Count from 1 to 30" in user:
            text = ", ".join(str(i) for i in range(1, 31))
            if not cheat and body.get("stop"):
                text = text.split(body["stop"][0])[0]
        elif temp and temp > 0:
            text = "fixed-answer" if cheat else f"answer-{rng.randrange(10**9)}"
        else:
            text = "OK"
        completion_tokens = len(reasoning) // 4 + len(text) // 4 + 1
        finish = "stop"
        if not cheat and completion_tokens > max_tokens:
            keep = max(1, max_tokens * 4 - len(reasoning))
            text = text[:keep] if keep > 0 else ""
            completion_tokens, finish = max_tokens, "length"
        if tool_calls:
            finish, text = "tool_calls", ""
        chunks: list[dict] = [{"id": "r1", "model": body["model"], "choices": [{"delta": {"role": "assistant"}}]}]
        if reasoning:
            chunks.append({"choices": [{"delta": {"reasoning_content": reasoning}}]})
        if tool_calls:
            chunks.append({"choices": [{"delta": {"tool_calls": tool_calls}}]})
        if text:
            chunks.append({"choices": [{"delta": {"content": text}}]})
        chunks.append({"choices": [{"delta": {}, "finish_reason": finish}]})
        chunks.append({"choices": [], "usage": {"prompt_tokens": prompt_tokens,
                                                 "completion_tokens": completion_tokens}})
        self._sse(chunks)


def test_e2e() -> None:
    print("e2e (fake API)")
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "endpoints.json"
        cfg.write_text(json.dumps({
            "endpoints": {
                "fake-official": {"role": "official", "base_url": f"{base}/honest/v1", "api_key_env": "FAKE_KEY",
                                  "model": "fake-1", "thinking": {"on": {"thinking": {"type": "enabled"}},
                                                                  "off": {"thinking": {"type": "disabled"}}}},
                "fake-honest": {"role": "plan", "base_url": f"{base}/honest/v1", "api_key_env": "FAKE_KEY",
                                "model": "fake-1", "thinking": {"on": {"thinking": {"type": "enabled"}},
                                                                "off": {"thinking": {"type": "disabled"}}}},
                "fake-cheater": {"role": "plan", "base_url": f"{base}/cheater/v1", "api_key_env": "FAKE_KEY",
                                 "model": "fake-1", "thinking": {"on": {"thinking": {"type": "enabled"}},
                                                                 "off": {"thinking": {"type": "disabled"}}}},
            },
            "audits": [{"model_slug": "fake-1", "reference": "fake-official", "targets": [
                {"endpoint": "fake-honest", "provider_slug": "p", "plan_slug": "honest"},
                {"endpoint": "fake-cheater", "provider_slug": "p", "plan_slug": "cheater"}]}],
        }))
        runs = Path(tmp) / "runs"
        env = {**os.environ, "FAKE_KEY": "x", "CODINGPLANS_ENDPOINTS_JSON": str(cfg),
               "CODINGPLANS_RUNS_ROOT": str(runs), "CODINGPLANS_REPORTS_DIR": str(Path(tmp) / "reports")}
        tests = "token_accounting,param_compliance,response_cache,tool_calls,reasoning_budget"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "audit" / "run_audit.py"), "--group", "fake-1", "--tests", tests,
             "--extra", "--n", "6", "--sleep-min", "0", "--sleep-max", "0"],
            env=env, capture_output=True, text=True, timeout=600,
        )
        calib = subprocess.run(
            [sys.executable, str(ROOT / "audit" / "run_audit.py"), "--group", "fake-1", "--tests", tests,
             "--calibrate", "--extra", "--n", "6", "--sleep-min", "0", "--sleep-max", "0"],
            env={**env, "CODINGPLANS_REPORTS_DIR": str(Path(tmp) / "calib")},
            capture_output=True, text=True, timeout=600,
        )
        server.shutdown()
        calib_rows = [r for p in (Path(tmp) / "calib").glob("*.json") for r in json.loads(p.read_text())["results"]]
        check(calib.returncode == 0 and len(calib_rows) == 5 and all(r["status"] == "pass" for r in calib_rows),
              f"official-vs-official calibration passes ({[r['status'] for r in calib_rows]})")
        check(proc.returncode == 1, f"audit exits 1 when a plan fails (got {proc.returncode})")
        if proc.returncode not in (0, 1):
            print(proc.stderr[-3000:])
            return
        reports = sorted((Path(tmp) / "reports").glob("*.json"))
        by_target = {json.loads(p.read_text())["target"]: json.loads(p.read_text())["results"] for p in reports}
        honest = {r["test_name"]: r["status"] for r in by_target.get("fake-honest", [])}
        cheater = {r["test_name"]: r["status"] for r in by_target.get("fake-cheater", [])}
        print(f"    honest:  {honest}\n    cheater: {cheater}")
        check(bool(honest) and all(s in ("pass", "inconclusive") for s in honest.values()), "honest plan never fails")
        for t in ("token_accounting", "param_compliance", "response_cache", "tool_calls", "reasoning_budget"):
            check(cheater.get(t) == "fail", f"cheater fails {t}")


def main() -> int:
    test_stats()
    test_schema_and_tool_calls()
    test_token_accounting()
    test_param_and_cache()
    test_reasoning_and_code()
    test_registry()
    if "--e2e" in sys.argv:
        test_e2e()
    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
