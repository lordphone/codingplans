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
- `needle_common` — `long_context/needle_common.py` (filler generator + insertion + grid helpers)

No empty placeholder families — every directory under `fidelity/` has at least one runnable test.
