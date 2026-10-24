# Benchmarking methodology review

_Date: 2026-06-02. Method: deep-research pass (6 search angles → 28 primary/secondary
sources → 117 extracted claims → 25 adversarially verified, 3-vote; 23 confirmed, 2
refuted) plus a direct read of the suite's code and design docs
(`fidelity/IMPROVEMENTS.md`, `fidelity/THREATS.md`, `performance/benchmark.py`)._

This document answers "am I doing benchmarking right?" in two halves: a **fact-check** of
the literature the suite's design rests on, and a **methodology critique** of the
measurement design itself. Confidence levels are explicit; anything not independently
verified in this pass is marked as such rather than asserted.

---

## 1. Top-line verdict

**The science you built on is sound, and your framing of it is honest.** Nearly every
load-bearing claim in `IMPROVEMENTS.md` checks out against primary sources, and — to your
credit — the doc's opening already states the single most important caveat correctly:
_"This suite is a drift detector, not a substitution proof."_ That is exactly the
conclusion the strongest source (Cai et al., 2504.04715) reaches. You did not oversell it.

**Where it's weak is statistics and labeling, not premise:**

1. **Fidelity suite** — the per-test *rationale* is well-grounded, but the suite draws
   pass/fail conclusions from sample sizes and point estimates that don't support them:
   N=5 per needle cell (≈ ±40% binomial CI), a quadratic curvature fit on 5–8 points with
   no CI, hand-set thresholds with no significance test, no multiple-comparisons control
   across 6 daily tests, and an entropy test that ships at N=200 when its own table calls
   for ~1,000.
2. **Performance probe** — methodologically the bigger issue. Single-stream sequential
   "TPS" measures single-request *decode speed*, not serving throughput; it reports one
   sample (not p50/p90/p99); and `pick_scenario()` randomizes the workload *per job*, so
   different providers in one matrix run are timed on different prompts and output
   lengths — which makes the cross-provider tokens/sec numbers not comparable.

Neither half is "wrong" so much as **claiming more precision than the design delivers.**
The fixes are mostly about honest labeling, CIs, and holding the workload constant.

---

## 2. Literature fact-check

### 2a. Confirmed (adversarially verified, high confidence)

| # | Claim (as used in your design) | Verdict | Source |
|---|---|---|---|
| 1 | Text-only black-box auditing detects same-base-model INT8/FP8 quantization at **near-chance** (~50%); software-only methods are "fundamentally unreliable" against subtle substitution. | **Confirmed** | Cai et al., [2504.04715](https://arxiv.org/abs/2504.04715) (Table 2: classifier accuracies "hover around 50%") |
| 1b | Logprobs give a much stronger signal, **but** no major provider exposes full logprobs and logprob methods are "defeated by inference nondeterminism in production." | **Confirmed** | Cai et al., [2504.04715](https://arxiv.org/abs/2504.04715) |
| 1c | "No universally applicable, robust software-based method exists" against a determined adversary; TEEs (hardware attestation) are the recommended robust path. | **Confirmed** | Cai et al., [2504.04715](https://arxiv.org/html/2504.04715v1) (verbatim conclusion) |
| 2 | Low-bit (INT4 / W4A16) PTQ causes large math drops (up to **32.4%** on Llama-3 MATH, avg 11.3%; up to ~70% in harder settings) while aggregate/MMLU loses little; FP8 ~lossless, INT8 1–3%. | **Confirmed** | [2501.03035](https://arxiv.org/html/2501.03035v2), [2505.11574](https://arxiv.org/abs/2505.11574), [2411.02355](https://arxiv.org/abs/2411.02355) |
| 2b | Quantization damage concentrates on **method/execution errors** (carries, rule application) over conceptual reasoning. | **Confirmed**; "multiplication-worst" is a weaker (2-1) sub-finding | [2505.11574](https://arxiv.org/abs/2505.11574), [2501.03035](https://arxiv.org/html/2501.03035v2) |
| 8 | T=0 / greedy decoding **is** non-deterministic in production; root cause is batch-size variation × non-batch-invariant kernels (not atomic adds). Identical weights stay token-identical then diverge. | **Confirmed** | Thinking Machines, [He et al. 2025](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) (Qwen3-235B: identical for 102 tokens, diverges at 103) |
| 10 | Vanilla NIAH saturates on modern models; harder RULER variants drop sharply with length; lexical-substring & contamination are real shortcuts to defeat. | **Confirmed** | RULER, [2404.06654](https://arxiv.org/abs/2404.06654) (NVIDIA, COLM 2024) |
| 11 | Lost-in-the-middle: recall is U-shaped vs. position, **even in explicitly long-context models**. | **Confirmed** | Liu et al., [TACL 2024](https://aclanthology.org/2024.tacl-1.9/) |
| 13 | A real vLLM **FP8 FlashAttention-3 kernel bug** dropped 128k NIAH from **91% → 13%** (imprecise FP32 accumulation past ~100K contraction dim); fixed to ~89% via two-level accumulation. | **Confirmed** | [vLLM blog 2026-04-22](https://vllm.ai/blog/2026-04-22-fp8-kvcache), [flash-attention PR #104](https://github.com/vllm-project/flash-attention/pull/104) |
| 9 | Rényi-2 (collision) entropy has **lower finite-sample estimation error** for its target than plug-in Shannon. | **Confirmed (with a nuance — see below)** | [2606.01218](https://arxiv.org/abs/2606.01218), [Cornell IT-Rényi notes](https://people.ece.cornell.edu/acharya/papers/it-renyi.pdf) |

### 2b. Refuted (verified 0-3) and overstated

| Item | Verdict | Note |
|---|---|---|
| The "**~1000× lower query budget** for logprob methods" figure | **Not in the source** | Cai et al. says logprobs are "stronger" but states **no** 1000× factor. Treat as an unsupported extrapolation — drop the specific number from your docs. |
| "RUT relies on **ranked token lists** rather than logprobs" | **Refuted (0-3)** | Zhu et al. RUT ([2506.06975](https://arxiv.org/abs/2506.06975)) requires **top-k log-probabilities** from the target **and** full reference logits. A purely text-only suite **cannot** run RUT — relevant to your "logprob path" future work in `THREATS.md`. |
| "RUT detects substitution in **~1000 queries**" | **Refuted (0-3)** | No such query-budget figure in the paper. |
| Divergence positions (swap ~tok 1–10, INT4 ~20–50, BF16 ~100) | **Only BF16 ≈100 is supported** | The token-103 Qwen3 figure backs the BF16/BF16 number; the swap and INT4 ranges are **unverified** — keep them as illustrative intuition, not measured facts. |
| Rényi-2 nuance | **Caveat** | Increasing N improves the estimate of **H₂ (collision entropy)**, which is a *different quantity* than Shannon H₁ (H₂ ≤ H₁). Fine as a relative shift detector, but label it "collision entropy," not a Shannon proxy. |

### 2c. Plausible but NOT independently verified in this pass

These are claims from `IMPROVEMENTS.md` that the research either fetched-but-didn't-rank
into the top-25 verified set, or couldn't tie to a primary source within budget. **Not
refuted — just unconfirmed.** Don't cite them as settled:

- **#3** per-digit metric "~10× more sensitive" than exact-match — directionally
  reasonable (more bits per sample) but the 10× figure is unsourced.
- **#4** first-digit-easy / last-digit-hard in long multiplication (Gambardella
  [2406.02356](https://arxiv.org/abs/2406.02356) was fetched but the specific claim wasn't verified).
- **#5** "~1000 evaluations to detect a 5–15% gap at p<0.01" — plausible power ballpark, unconfirmed.
- **#6** BPE tokenizer shortcuts (palindromes/repdigits/round numbers) washing out signal.
- **#7** CoT-stripping *maximizes* the INT4 signal.
- **#12** KV-cache error concentrates in the **middle** (attention-sink + recency) →
  "smile." The components (StreamingLLM sinks, lost-in-the-middle) are confirmed; the
  *combined causal mechanism producing the smile* was not verified as one claim.
- **#14** Chen/Zaharia/Zou GPT-4 prime 97.6%→2.4% drift + its critiques (this is real and
  famous, and the well-known critique is that the "primes" were all actually prime so the
  model's switch to answering "composite" looked catastrophic — but the workflow didn't
  surface a verified quote, so treat as unconfirmed-here).
- **#15** multiple-comparisons / Bonferroni-BH need — textbook-correct (see §3), but not
  among the verified claims.
- **#16** count+sum disambiguation — sound experimental design on its face (independent
  2-of-2 signal), citation-independent.

---

## 3. Methodology critique — fidelity suite

The premise is fine; these are about **the strength of the conclusions you can draw.**

1. **Sample size vs. per-cell claims (highest impact).** N=5 per needle cell gives a
   binomial 95% CI of roughly **±40%** on a single cell's recall. That is too wide to
   conclude anything *per cell*. Two honest options: (a) raise N substantially where
   budget allows, or (b) stop interpreting individual cells and only report statistics
   pooled across many cells (with a CI). Arithmetic at N=20 × 100 prompts is in far better
   shape.

2. **No confidence intervals or significance tests on the gap statistics.** Every
   `fail` is a point estimate vs. a hand-set threshold (digit-gap 0.02, recall-gap 0.20,
   curvature-gap 0.50). Best practice is to **bootstrap a CI on the gap** and fire only
   when the CI excludes zero (or the threshold) — otherwise a "fail" can be noise,
   especially at N=5. The thresholds themselves read as reasonable guesses; deriving them
   from the measured noise floor (run ref-vs-ref and see how big the gap gets by chance)
   would calibrate them.

3. **Quadratic curvature fit (multi-needle smile).** Fitting `a + b·d + c·d²` to ~5–8
   depth points leaves very few residual DoF; thresholding `c` at 0.50 with no CI is
   fragile. Bootstrap the fit and report the curvature **with its CI**. Also: lost-in-the-
   middle (confirmed, §2a #11) produces a smile in BF16 too, so the *reference* already has
   `c > 0` — your "healthy-lengths" gating and target-minus-reference framing handle this,
   but the interpretation note should stay loud.

4. **Entropy test is under-powered by its own standard.** Code ships N=200
   (`test_entropy.py:75`); your own table says Rényi-2 wants ~1,000 for a clean 0.2-bit
   estimate, and the effect (0.05–0.3 bit) sits at the bias floor. You already call this
   "the most fragile test." Recommendation: **never fire on entropy alone** — keep it as a
   soft corroborator only, or raise N toward 1,000. And label the statistic "collision
   entropy (H₂)" per the §2b nuance.

5. **Multiple comparisons.** Running ~6 tests (some with many per-cell sub-tests) daily
   without FWER/FDR control inflates the false-alarm rate. Apply Benjamini-Hochberg across
   the test battery before alerting. (Textbook; see [FDR/Bonferroni notes](https://physiology.med.cornell.edu/people/banfelder/qbio/resources_2008/1.5_Bonferroni_FDR.pdf).)

6. **Reference vs. target captured days apart (real confound).** `assert_comparable()`
   gates on panel identity, not *time*. Provider-side A/B routing, time-of-day load, and
   silent version bumps all drift between a ref run and a target run taken on different
   days. Best practice is **contemporaneous paired sampling**: interleave ref and target
   calls in the same wall-clock window so temporal confounds cancel. Today's design can't
   distinguish "the plan quantized the model" from "the official endpoint changed last
   Tuesday."

7. **Ceiling (already acknowledged, restated for completeness).** Per Cai et al., a
   strictly text-only detector cannot reliably catch a competent same-base-model INT8/FP8
   swap. Your suite targets the *detectable* regime (gross swaps, naive INT4, catastrophic
   kernel bugs like the FP8 FA3 incident), which is the right scope — keep being explicit
   that a clean quant can pass.

---

## 4. Methodology critique — performance probe

This is where the framing diverges most from industry best practice (NVIDIA GenAI-Perf,
MLPerf Inference, Artificial Analysis, Anyscale LLMPerf).

1. **"TPS" from single-stream sequential requests is decode speed, not throughput.** One
   request at a time measures **single-request decode rate** (≈ 1/TPOT at concurrency=1),
   which is a *latency* metric. Serving **throughput/capacity** requires a **concurrency
   sweep** (throughput vs. number of concurrent requests). Relabel the current number as
   "single-stream decode speed (TPOT⁻¹)" and, if you want capacity, add a concurrency
   sweep. ([NVIDIA LLM benchmarking fundamentals](https://developer.nvidia.com/blog/llm-benchmarking-fundamental-concepts/), [MLPerf Inference v5](https://mlcommons.org/2025/04/llm-inference-v5/))

2. **One sample per job → report distributions.** A single measurement per (provider,
   model) has no error bars. Canonical practice is repeated runs reported as
   **p50/p90/p99** for TTFT, TPOT/ITL, and end-to-end latency, with a warmup request
   discarded. ([Artificial Analysis methodology](https://artificialanalysis.ai/methodology/performance-benchmarking))

3. **Workload isn't held constant (comparability bug).** `benchmark.py` calls
   `pick_scenario()` *per job* (`benchmark.py:520`), so within one matrix run different
   providers get **different prompts and different output lengths**. TPS depends strongly
   on both. Fix: a **fixed canonical prompt set + fixed `max_tokens`** across all
   providers in a comparison run. (Randomizing across *runs* for stealth is fine; the
   issue is randomizing *within* a single comparison.)

4. **Cross-provider tokens/sec is apples-to-oranges.** Tokenizers differ, so "tokens per
   second" isn't directly comparable across vendors for the same text. Either normalize by
   characters/bytes, or surface the caveat prominently. The `len//4` fallback estimator
   makes this worse for providers that don't report usage.

5. **TTFT for reasoning models.** You define TTFT as time-to-first-**visible-content**
   token, which folds queueing + prefill + hidden thinking into one number for thinking
   models — not comparable to a non-thinking model's TTFT. The code already captures
   reasoning timings (`ttft_reasoning_s`, etc.); surface them and report TTFT-to-any-token
   separately.

6. **Network/geographic latency is inside TTFT.** A provider's TTFT here includes your
   round-trip. Note the measurement location, or measure from a fixed/colocated host.

---

## 5. Prioritized recommendations

**Do first (cheap, fixes correctness of conclusions):**
- [ ] Hold the performance workload constant across providers in a comparison run (fixed
  prompts + `max_tokens`). One-line-ish change around `benchmark.py:520`.
- [ ] Relabel single-stream "TPS" as single-request decode speed; stop implying it's
  serving throughput.
- [ ] Stop firing fidelity pass/fail on entropy alone; demote to corroborator.
- [ ] Remove the unsupported "~1000×" logprob figure and soften the divergence-position
  numbers in `IMPROVEMENTS.md`; relabel Rényi-2 as collision entropy (H₂).

**Do next (statistical rigor):**
- [ ] Bootstrap CIs on every gap statistic (digit gap, recall gap, curvature); fire only
  when the CI excludes the threshold.
- [ ] Calibrate thresholds from a **ref-vs-ref** run (measure the chance gap, set
  thresholds above it) instead of hand-setting.
- [ ] Add Benjamini-Hochberg FDR control across the test battery before alerting.
- [ ] Raise needle N, or only report cell statistics pooled with a CI (never per-cell).
- [ ] Report perf metrics as p50/p90/p99 over repeated samples with a warmup.

**Strategic (bigger projects, already in `THREATS.md`):**
- [ ] Contemporaneous paired ref/target sampling to kill temporal confounds.
- [ ] Logprob path where providers expose `top_logprobs` — but note RUT also needs
  reference logits, and logprob methods are defeated by production nondeterminism, so this
  raises the ceiling only modestly. TEEs are the only robust path and are out of scope.
- [ ] Add a concurrency sweep if you want a real throughput/capacity number.

---

## 6. Sources (primary unless noted)

- Cai et al., "Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs" — [arXiv 2504.04715](https://arxiv.org/abs/2504.04715)
- Zhu et al., rank-based uniformity test (RUT) — [arXiv 2506.06975](https://arxiv.org/abs/2506.06975)
- "Quantization Meets Reasoning" — [arXiv 2505.11574](https://arxiv.org/abs/2505.11574)
- Low-bit quantization & arithmetic — [arXiv 2501.03035](https://arxiv.org/html/2501.03035v2)
- Llama-3.1 quantization at scale (FP8 lossless / INT8 1–3% / INT4 competitive) — [arXiv 2411.02355](https://arxiv.org/abs/2411.02355)
- RULER long-context benchmark — [arXiv 2404.06654](https://arxiv.org/abs/2404.06654)
- Liu et al., "Lost in the Middle" — [TACL 2024](https://aclanthology.org/2024.tacl-1.9/)
- vLLM FP8 KV-cache / FA3 NIAH regression — [vLLM blog 2026-04-22](https://vllm.ai/blog/2026-04-22-fp8-kvcache), [flash-attention PR #104](https://github.com/vllm-project/flash-attention/pull/104)
- He et al., "Defeating Nondeterminism in LLM Inference" — [Thinking Machines Lab, 2025](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)
- Rényi/collision entropy estimation — [arXiv 2606.01218](https://arxiv.org/abs/2606.01218), [Cornell IT-Rényi notes](https://people.ece.cornell.edu/acharya/papers/it-renyi.pdf)
- Gambardella et al. (long multiplication) — [arXiv 2406.02356](https://arxiv.org/abs/2406.02356)
- Chen, Zaharia, Zou, "How Is ChatGPT's Behavior Changing over Time?" — [arXiv 2307.09009](https://arxiv.org/abs/2307.09009)
- LLM serving benchmark methodology — [NVIDIA GenAI-Perf fundamentals](https://developer.nvidia.com/blog/llm-benchmarking-fundamental-concepts/), [NVIDIA NIM metrics](https://docs.nvidia.com/nim/benchmarking/llm/latest/metrics.html), [MLPerf Inference v5](https://mlcommons.org/2025/04/llm-inference-v5/), [Artificial Analysis methodology](https://artificialanalysis.ai/methodology/performance-benchmarking)
- Multiple comparisons (Bonferroni/FDR) — [Cornell qBio notes](https://physiology.med.cornell.edu/people/banfelder/qbio/resources_2008/1.5_Bonferroni_FDR.pdf)

_Caveat on this review: the fact-check confirmations are 3-vote adversarially verified and
high-confidence. The performance-methodology critiques (§4) reflect industry-standard
guidance from the sources above but were not each individually 3-vote verified in this
pass; they're well-established best practice rather than contested findings. Items in §2c
are explicitly unconfirmed, not endorsed._
