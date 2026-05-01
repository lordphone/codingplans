# Fidelity threat → test matrix

Which test catches which audit-bait behavior, and what's still TODO.

| Threat | Primary test | Complementary |
| --- | --- | --- |
| INT4 weight quantization | `arithmetic` — direct numerical precision signal, hardest for INT4 to fake | `rollout_prefix` — long structured output diverges at token level |
| Model swap | `rollout_prefix` — byte-level output fingerprint, strongest signal for family-level swap | `arithmetic` — smaller models fail differently on large multiplications |
| KV cache quantization | `multi_needle` — selective middle-depth forgetting is the KV cache signature | `aggregation` — missed values scattered across context |
| Context truncation | `aggregation` — undercounts are unambiguous and length-correlated | `single_needle` grid — hard cliff shape confirms truncation threshold |

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
- **Multi-test correction**: running six tests daily without
  Bonferroni / Benjamini–Hochberg correction will produce spurious
  alerts; the harness that aggregates results across tests should
  apply FWER control.
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
