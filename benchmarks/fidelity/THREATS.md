# Fidelity threat → test matrix

Which test catches which audit-bait behavior, and what's still TODO.

| Threat | Primary test | Complementary |
| --- | --- | --- |
| INT4 weight quantization | `arithmetic` — direct numerical precision signal, hardest for INT4 to fake | `rollout_prefix` — long structured output diverges at token level |
| Model swap | `rollout_prefix` — byte-level output fingerprint, strongest signal for family-level swap | `arithmetic` — smaller models fail differently on large multiplications |
| KV cache quantization | `multi_needle` — selective middle-depth forgetting is the KV cache signature | `aggregation` — missed values scattered across context |
| Context truncation | `aggregation` — undercounts are unambiguous and length-correlated | `single_needle` grid — hard cliff shape confirms truncation threshold |
| Broken / degraded tool calling (chat-template bugs, quantization, constrained-decoding shortcuts) | `tool_calls` — schema accuracy + trigger similarity vs official (Kimi Vendor Verifier method) | `code_exec` |
| Hidden system-prompt injection | `token_accounting` — constant `prompt_tokens` surplus (intercept) for byte-identical requests | — |
| Usage / quota inflation, different tokenizer (= different model) | `token_accounting` — slope > 1, completion tokens per char | `rollout_prefix` |
| Silently ignored `max_tokens` / `stop` / JSON mode / temperature; clamped output cap | `param_compliance` | `entropy` (temperature) |
| Answer caching (exact or semantic) | `response_cache` — duplicate rate at T=1, stale nonce echo | — |
| Reasoning budget cut / thinking disabled | `reasoning_budget` — reasoning length ratio, thinking presence, accuracy | `code_exec` |
| General coding-quality regression | `code_exec` — hidden unit-test pass rate on fresh tasks | `tool_calls` |
| Peak-hour throttling | `audit/run_performance.py` 4×/day (TPS p10, TTFT p90, error rate by hour) | — |

## Status

Implemented under `model_identity/`:
- `arithmetic` — `model_identity/test_arithmetic.py`
- `rollout_prefix` — `model_identity/test_rollout_prefix.py`
- `entropy` — `model_identity/test_entropy.py` *(not in the matrix; sampling-distribution sanity check, secondary signal for weight quantization)*

Implemented under `long_context/`:
- `needle_single` — `long_context/test_needle_single.py` (2D length × depth grid)
- `needle_multi` — `long_context/test_needle_multi.py` (K needles per prompt)
- `needle_aggregation` — `long_context/test_needle_aggregation.py` (M scattered values, sum)
- `needle` — `long_context/needle.py` (filler generator + insertion + grid helpers)

Implemented under `agentic/`, `integrity/`, `reasoning/`, `coding/` (2026-10):
- `tool_calls` — `agentic/test_tool_calls.py`
- `token_accounting`, `param_compliance`, `response_cache` — `integrity/`
- `reasoning_budget` — `reasoning/test_reasoning_budget.py`
- `code_exec` — `coding/test_code_exec.py` (sandboxed execution, see `coding/sandbox.py`)

`benchmarks/audit/run_audit.py` runs any tier of these per audit group and
applies Benjamini–Hochberg across each plan's tests (closes the
"multi-test correction" gap below); `--calibrate` runs official vs official.
`benchmarks/selftest.py --e2e` proves each new test fails a simulated cheater
and passes an honest endpoint.

No empty placeholder families — every directory under `fidelity/` has at least one runnable test.

## Known gaps (future work)

The literature is clear that text-output-only INT4 detection has limited
power against a sophisticated adversary. The high-leverage follow-ups
this suite does not yet implement:

- **Logprob-based fallback** (`entropy`, `arithmetic`): when a provider
  returns `logprobs`, KL-divergence and rank-based uniformity tests
  (RUT, "Log Probability Tracking" arXiv 2512.03816) detect the same
  shifts at ~1000× lower query budget. The entropy test in particular
  is severely sample-starved without logprobs and should auto-promote
  when they are available.
- ~~**Multi-test correction**~~ — done: BH in `audit/run_audit.py`.
- **Knowledge-boundary fingerprint (KBF)**: binomial test on questions
  just past each model's knowledge cutoff; reported to catch 155/155
  substitutions in ~100–700 probes (arXiv 2605.29524). Best next test for
  model swaps that survive `rollout_prefix` (forced-thinking models).
- **Prompt-cache honesty**: cached_tokens reported vs TTFT actually saved.
- **Quota audit**: does the advertised N-requests-per-5h hold before 429s.
  Expensive and ToS-sensitive; see docs/research/cheating-vectors.md §2.7.
- **Anthropic-compatible path**: plans are mostly consumed via
  `/anthropic` endpoints by Claude Code; translation-layer bugs there are
  invisible to the OpenAI-path tests (research §2.16).
- **Time-series drift detection**: CUSUM / EWMA on test statistics
  for daily monitoring (vs the current point-in-time fail flag).
- **vLLM batch-invariant anchor**: mirror a subset of tests against a
  self-hosted vLLM with batch-invariant kernels of the same open-weight
  model the provider claims to serve; the only way to detect a covert
  swap from BF16 to a same-quality alternative.
- **Periodic panel rotation**: `panel_id` is bumped manually at panel
  content changes; a determined provider that hashes prompts can route
  benchmark queries to the genuine model. Rotating the panel id (or
  filler seed) on a schedule is a defense.

These are out of scope for the per-test design but tracked here so
audits know what the suite does *not* cover.
