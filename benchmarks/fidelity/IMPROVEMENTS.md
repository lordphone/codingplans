# Why each fidelity test does what it does

This is a plain-English walkthrough of the statistical and methodological
choices in the six fidelity tests, aimed at "I wrote this six months ago
and want to remember why." Each section explains: **what we measure**,
**why that specific metric and not the obvious one**, and **what
attacks/confounds it defends against**.

Read alongside [`THREATS.md`](THREATS.md) (which threats each test
catches) and the literature review at
`/Users/lordphone/Downloads/compass_artifact_wf-...md` (the source for
most of this).

## The single most important framing

There is one finding that constrains every test in this suite. The
Berkeley paper "Are You Getting What You Pay For?" (Cai et al.,
arXiv 2504.04715) showed that **text-only black-box auditing detects an
INT8/FP8 substitution at roughly chance accuracy** when the substituted
variant is a quantization of the same base model. Once you have access
to logprobs the picture flips — RUT and "Log Probability Tracking"
detect quantization with ~1000× lower query budget than text-only.

That means:

- This suite is a **drift detector**, not a substitution proof.
- Every test makes design choices to extract the maximum possible
  signal from text-only output.
- When a provider does return logprobs, we are leaving a lot on the
  table by not using them — that is the biggest known gap and is
  documented in `THREATS.md`.

The rest of this doc explains the per-test choices that flow from this
framing.

---

## 1. `test_arithmetic.py` — INT4 weight-quantization signal

### The premise

Long multiplication is unusually quantization-sensitive. Several papers
("Quantization Meets Reasoning" arXiv 2505.11574 and 2501.03035) show
INT4 of Qwen2.5 / LLaMA-3 has up to **32% accuracy drop on math** while
MMLU drops <1%. The degradation concentrates on **method/execution
errors** — carries and digit lookups — rather than high-level reasoning.
That is why arithmetic is a better INT4 detector than a knowledge
benchmark would be.

### Why per-digit scoring

Whole-string equality (`parsed == expected`) throws away most of the
signal. Imagine a 9-digit answer where the model gets the first 8 right
and only the last digit wrong: whole-string says **MISS**, per-digit
says 8/9 = 0.89. The literature finds the per-digit metric is **roughly
10× more statistically sensitive** than whole-string match.

Implementation: align right-to-left, zero-pad to the longer width, count
matching positions:

```
expected: 12345678
parsed:   12345670     →   7/8 = 0.875 digit accuracy
```

We also separately track **first-digit** and **last-digit** accuracy.
The Gambardella et al. paper (arXiv 2406.02356) shows the first digit
of a long product is "easy" (depends on few carries) and the **last
digit is hardest** (depends on the most carry chains). So under
quantization you'd expect last-digit accuracy to fall faster than
first-digit accuracy — that pattern is its own diagnostic.

### Why N=20 samples per prompt

Small N is fatal here. With N=3, the modal-answer statistic is
meaningless: a single sample is the mode 3/3 of the time, and the
"mode-frequency" signal can only take values {1/3, 2/3, 1}. The
literature recommends ~20 samples × ~50 prompts = ~1000 evaluations
to detect a 5–15% accuracy gap at p<0.01. Our panel is 100 prompts so
N=20 puts us at 2000 calls per run.

### Why mode-frequency matters separately from accuracy

Even when the modal answer is correct, **how often the mode wins** is a
quantization signature. Flatter logits break ties more often — at T=0
two different completions can come out of the same model on different
batch contexts (the Thinking Machines batch-invariance result), and the
frequency at which they agree is itself a measurement.

A typical signature: BF16 baseline mode-freq = 0.95+ (essentially
always agrees with itself), INT4 quantization mode-freq drops to
0.7–0.85 even when the correct answer still wins.

### Why we filter "trivial" operands

The research warns that multiples of 1000, palindromes (4554, 12321),
and repdigits (7777) collide with high-probability single-token
patterns in BPE tokenizers. The model can answer those correctly even
under heavy quantization because the answer is "memorized" as a token
shortcut rather than computed. Including them washes out the
quantization signal.

```python
def _is_trivial_operand(n: int) -> bool:
    s = str(n)
    if n % 1000 == 0: return True
    if s == s[::-1]: return True   # palindrome
    if len(set(s)) == 1: return True   # repdigit
    if s.endswith("00") or s.endswith("000"): return True
    return False
```

### Why 40/40/20 split across 4×4/5×5/6×6 digits

Below 3-digit×3-digit, even INT4 saturates at 100% — no gap, no signal.
Above 6×6 digits, even BF16 frontier models drop near zero — the gap
collapses to noise. The sweet spot is 4×4 and 5×5; we keep some 6×6 to
detect models that gracefully degrade past the easy regime.

### Why no chain-of-thought

Quotation from the literature: "Strip CoT. A single-shot 'Answer with
only the number' prompt with no CoT maximizes the INT4 signal."
Reasoning tokens give the model room to **compensate** for quantization
noise — the model effectively re-derives the answer step by step,
catching its own carry errors. Without CoT, each digit position
depends on a single forward pass through near-tied logits; that is
exactly the regime where INT4 noise breaks ties differently from BF16.

The system prompt forbids reasoning explicitly:

> "answer with only the integer — no thinking out loud, no
> step-by-step work, no prose, no markdown, no code fences, no
> commas, no scientific notation, no leading zeros."

### Fail threshold

`FAIL_THRESHOLD_GAP = 0.02` on the digit-accuracy gap. Tighter than the
old whole-string threshold (0.05) because per-digit is ~10× more
sensitive. If the gap exceeds 2% we flag it; the per-prompt and
last-digit breakdowns let you read **where** the gap is.

---

## 2. `test_rollout_prefix.py` — model-swap and divergence signal

### Why this test exists at all

Two endpoints serving the same weights at T=0 should produce **almost**
identical long completions. They won't be byte-identical (Cai et al. and
Thinking Machines both confirm this — batch-invariance noise makes T=0
non-deterministic in production). But they will agree for many tokens
before diverging, and that divergence-position is a fingerprint of the
weights.

A model swap (different family, different size, different fine-tune)
typically produces divergence at token 1–10. INT4 quantization of the
same model produces divergence around tokens 20–50. BF16/BF16 produces
divergence around token ~100 on average.

### Why mean pairwise cross-pair, not modal-vs-modal

The naive metric is `common_prefix(modal_ref, modal_tgt)`: take the
most-common completion from each side and compare them. This breaks
because at T=0 with N=10 long completions per prompt, **all 10
completions are unique** — `modal()` returns the lexicographically
first one, which is essentially `r_samples[0]`. So the inter-side
metric becomes `common_prefix(r[0], t[0])` — a single random pair. Huge
variance, no signal.

The fix is **mean pairwise prefix across all N×M cross-pairs**:

```python
def mean_pairwise_prefix(a_samples, b_samples):
    return mean(common_prefix(a, b) for a in a_samples for b in b_samples)
```

With N=M=10 that's 100 (a, b) pairs per prompt averaged. The variance
collapses, and the comparison becomes against the **intra-side floor**
(mean pairwise prefix within one side's own samples) — which captures
each provider's batch-invariance noise level.

The healthy ratio is `inter / min(intra_ref, intra_tgt) ≈ 1`. A model
swap drives that ratio toward 0; a quantization swap drives it
somewhere in between.

### Why text normalization

Some providers run a safety/rewrite post-process that swaps "smart"
quotes (`"` → `"`), em-dashes, or NBSP characters into the response.
Without normalization, a strict character-level prefix-match fires on
those rewrites and looks identical to a model swap. We NFKC-normalize,
fold smart quotes/dashes back to ASCII, and collapse whitespace before
the comparison.

```python
_PUNCT_FOLD = {ord("'"): "'", ord("'"): "'", ord("""): '"', ord("""): '"',
               ord("–"): "-", ord("—"): "-", ord("−"): "-", ord(" "): " "}
```

### Why we keep modal-vs-modal as a side report

Even though we don't use it as the primary statistic, the modal-vs-modal
prefix length is useful for human inspection of the per-prompt JSONL
log. When you're staring at a single failed prompt trying to figure out
*where* the divergence is, you want one canonical "this is where ref
splits from tgt" pair to look at.

---

## 3. `test_entropy.py` — sampling-distribution shape signal

### Honest framing first

This is the most fragile test in the suite. The expected effect size of
INT4 on first-token entropy is **0.05–0.3 bits**, and the plug-in
Shannon entropy estimator has bias of ~0.3 bits at N=200. We are
operating very close to the noise floor.

Provider-side logit warping (top-k, repetition penalty, frequency
penalty) can also shift entropy by similar amounts in **either**
direction, on top of any quantization signal. So this test is best
read as "did *something* change in the sampling distribution," not
"did INT4 happen specifically."

The right fix is to use logprobs when available (KL divergence has
~1000× the power of plug-in Shannon at the same N). That is the
biggest gap in this suite and is tracked in `THREATS.md`.

### Why Renyi-2 (collision entropy) over Shannon

Renyi-2 entropy is `−log₂(Σ pᵢ²)`. The plug-in estimator has much lower
bias than Shannon at moderate N because it depends only on the **second
moment** of the distribution, which converges faster than the
log-moments Shannon depends on. Concretely:

| Estimator | N for clean estimate of 0.2-bit shift |
| --------- | ------------------------------------- |
| Shannon (Miller-Madow corrected) | ~10,000 |
| Renyi-2 (collision) | ~1,000 |
| rank-1 mass (probability of mode) | ~200 |

So we report all three, with Renyi-2 as the primary statistic and rank-1
as a corroborator.

### Why the threshold is symmetric

INT4 quantization typically **raises** entropy (flatter logits → more
uncertainty at sampling). But provider-side top-k truncation
**lowers** entropy (the tail is killed off). Both are honest fidelity
signals. We test `|log₂(ratio)| > log₂(1.15)` so either direction
fires.

### Why the improved `first_word`

The original `first_word` was just whitespace-bounded. That meant
`"Redis."` and `"Redis"` and `"redis"` were three different buckets,
and the entropy estimate was inflated by stray punctuation that has
nothing to do with the underlying model.

The new normalization case-folds and strips leading/trailing
punctuation:

```
"Redis."   → "redis"
'"Redis".' → "redis"
"Redis"    → "redis"
```

Same bucket. Now the entropy estimate measures actual model-output
diversity rather than punctuation drift.

### Why we don't fall back gracefully on degenerate prompts

If a prompt has effectively one answer ("What's 2+2?" → "4" with
probability ~1.0), the reference's Renyi-2 entropy is near zero and
the ratio explodes. We exclude those prompts from the ratio
aggregation but still report them in `per_prompt`. The rank-1 mass
metric handles this case more gracefully — it just trends toward 1.0
for both sides without dividing by zero.

---

## 4. `test_needle_single.py` — context-truncation signal

### Why this isn't the obvious "find the password" test

Original NIAH (Kamradt 2023) saturates: every modern frontier model
gets 100% on a 32K context single-needle test. The literature
("RULER" arXiv 2404.06654) found that "almost all models exhibit
large performance drops as context length increases" on **harder**
NIAH variants — but only when you defeat two shortcuts:

1. **Lexical-substring attention.** If the needle is the only
   sentence containing "San Francisco" and the question asks about
   "San Francisco", the model wins by string match without long-context
   comprehension. We use a **paraphrased query** + **distractor
   needles** with the same shape:

   ```
   Needle:    # OPERATIONAL_TOKEN_CURRENT = QFXR7-MTPL3
   Distractor: # OPERATIONAL_TOKEN_LEGACY  = AAAAA-BBBBB
   Distractor: # OPERATIONAL_TOKEN_RETIRED = YYYYY-ZZZZZ
   Query: "Find the *current* operational token (NOT _LEGACY,
           _RETIRED, _STAGING, or any other suffix)..."
   ```

   Now the model has to actually attend to the suffix string in the
   right line — pure substring matching gives you three candidates, not
   one.

2. **Parametric knowledge / contamination.** Don't use Paul Graham
   essays as filler. We generate Python-shaped synthetic filler
   procedurally with a fixed seed; the haystack at length L is a
   strict prefix of length 2L, so length effects are isolated from
   "different filler bytes" effects.

### Why the length axis is the truncation signal, not the depth axis

This is the most important interpretation note for this test. Both
**lost-in-the-middle** (a real BF16 transformer property — Liu et al.
TACL 2024) and **KV-cache quantization** produce a U-shaped recall
curve along the depth axis. So the depth axis cannot distinguish them.

But **truncation** has a unique signature on the **length axis**: a
sharp transition between two adjacent length columns. Below the
truncation threshold, recall is fine; above it, recall collapses to
zero (or to "first-half-of-haystack only").

We therefore added the `_max_length_cliff` statistic: the largest
recall drop between any two consecutive length columns on each side.
The `cliff_drop_gap_target_minus_ref` field tells you whether the
target's cliff is sharper than the reference's. A positive value (>~0.3)
is the truncation fingerprint.

### Why N=5

Research recommends N≥10 to get the binomial 95% CI inside ±10% per
cell. N=5 is a cost compromise (5 lengths × 5 depths × 5 samples = 125
calls per run). Bump `--n` if you can afford it; the panel and
comparator both scale.

### Why the lengths go up to 128K characters (~37K tokens)

The original v1 grid topped out at 32K *characters* (~9K tokens) —
below where most modern long-context models would even start to
truncate. A 128K-token model could pass the entire v1 grid with
truncation set to 16K and we'd never see it. The new ceiling spans
typical truncation regimes (16K, 32K, 64K, 128K context windows).

---

## 5. `test_needle_multi.py` — KV-cache quantization signal

### The smile shape

This is the core diagnostic. KV-cache quantization (KIVI, KVQuant, SKVQ)
introduces error in the cached attention representation that **grows
with cache size and concentrates in middle positions**. The reasoning:

- Tokens near the start are protected by **attention sinks** (Xiao
  et al., StreamingLLM).
- Tokens near the end are protected by **recency bias** (the most
  recent few hundred tokens get full attention weight).
- Tokens in the **middle** get neither — they accumulate quantization
  error proportional to sequence length.

So under KV-cache quant, the per-depth recall curve dips in the
middle: high at d=0 and d=1, low at d=0.5. Drawn as a smile.

### Why fit a quadratic

If `y = a + b·d + c·d²` with `d, y ∈ [0, 1]`, then a smile (recall
high at edges, low in middle) is a parabola opening upward, which
means **`c > 0`**. KV-cache quantization deepens the smile relative to
the BF16 baseline, so `target_c > reference_c` is the signature.

⚠️ Sign-convention note: the source research wrote "more negative
curvature coefficient" but with this parameterization that's
inconsistent. `y = recall(depth)` with a U-shape has positive leading
coefficient. We chose to follow the math, not the literature wording.
The synthetic smoke test confirms: a synthetic smile yields `c ≈ +4.85`,
a flat synthetic baseline yields `c ≈ 0`.

### Why "more negative" in the original research is wrong (or confusingly worded)

Research said: "test whether the curvature coefficient is significantly
more negative than the BF16 baseline's." But:

- LITM (BF16 baseline) is already a U-shape recall curve = positive c.
- KV-cache quant makes the U deeper = MORE positive c.
- Therefore `target_c > reference_c`, gap is positive, not negative.

Either the research was using a different parameterization (e.g.
`y = peak − c·(d − 0.5)²`, in which case `c > 0` is also a smile and
"more positive" is what we want — same conclusion), or it was a
typo. Trust the math; we test for `target_c − reference_c > +0.5`.

### Why K=8 and not 5

Research says "K=8–10 is the sweet spot — large enough to fit a
quadratic curve and not so large that the needles themselves saturate
the context." With K=5 the quadratic fit has 2 residual degrees of
freedom — basically untestable. K=8 gives 5 residual DoF, enough to
detect a real curvature shift.

### Why we gate to "healthy lengths" before fitting the smile

This is subtle. Imagine the target is truncating context at 32K. At
lengths > 32K, the target loses **all** needles past the truncation
point — recall goes to zero across all depths. If you average per-depth
recall across all lengths (truncated and non-truncated), you contaminate
the depth curve with zero-recall noise from the truncated lengths and
the smile fit becomes meaningless.

So we only aggregate the depth curve over **healthy lengths** —
lengths where the *reference's* overall recall is ≥ 0.5. That way
the smile fit is computed on contexts where the model is genuinely
demonstrating recall, not on contexts where it's already truncating.

### Two ways this test fires

1. `recall_gap > 0.20`: target recall is 20% worse than reference.
   Generic "target is worse" — also catches truncation as a side
   effect.
2. `curvature_gap > 0.50`: target's smile is sharper than reference's
   even when overall recall is similar. The KV-cache-specific signal.

Either condition triggers a fail.

### Limitations the research is honest about

This test will likely **not** detect competent KIVI-class INT4 KV-cache
quantization (per-channel keys, per-token values). It will detect:

- Naive per-tensor INT4 KV-cache (which still happens).
- Catastrophic kernel bugs (the FP8 FlashAttention3 case where vLLM
  saw NIAH drop from 91% to 13%).
- FP4 KV-cache.

A clean state-of-the-art KV-cache quant will pass this test. That's a
known gap.

---

## 6. `test_needle_aggregation.py` — count-and-sum disambiguation

### Why ask for both count AND sum

This is the single most important design choice in this test. The
research is explicit:

> "Add **two ground-truth signals** per query: ask for both the
> *count* of integers and the *sum*. If count is wrong, it's a
> recall/truncation issue. If count is right but sum is wrong, it's
> an arithmetic issue. This is a **critical disambiguation step**."

Concretely, the prompt asks for:

```
count=<number of comment lines you found>
sum=<sum of all the integers>
```

And the comparator's `_diagnose()` produces three labels:

| Count error | Sum error | Diagnosis |
| ----------- | --------- | --------- |
| ≤ threshold | ≤ threshold | `ok` |
| > threshold | (any) | `truncation_or_recall_loss` |
| ≤ threshold | > threshold | `arithmetic_or_kv_quant` |

Without the count, a sum-undercount could be truncation, KV-cache
forgetting, or arithmetic drift — three completely different causes
that need different responses. With the count we can tell them apart.

### Why indexed needles in depth order

We tag each needle with an index assigned in **depth order** — index 1
is the shallowest, index M is the deepest:

```
# COUNT_VALUE_1 = 42   (at depth 0.04)
# COUNT_VALUE_2 = 17   (at depth 0.13)
...
# COUNT_VALUE_12 = 88  (at depth 0.97)
```

This sets up a downstream diagnostic the comparator does not yet
fully exploit but the JSONL log records: **the pattern of missing
indices**. Truncation produces a contiguous tail of misses (e.g.
"got 1..7, missed 8..12"). KV-cache quant produces a scattered
("swiss-cheese") pattern (e.g. "got 1, 3, 4, 7, 9, 12; missed 2, 5,
6, 8, 10, 11"). The current report doesn't compute the contiguity
statistic, but the indexed prompts make that an easy follow-up
analysis on the JSONL forensic log.

### Why values in [10, 99]

Two-digit integers are wide enough that wrong-answer collisions are
unlikely (a truncated model can't coincidentally pick the same wrong
sum). They're narrow enough that arithmetic isn't itself the
limiting factor — `sum([12, 47, 88, ...])` is well within any
modern model's working memory if it can read all the values.

### Why N=5 and lengths 8K–128K chars

Same reasoning as `test_needle_single.py`. N=5 keeps the call budget
manageable; the length grid spans truncation regimes for typical
modern long-context models.

### Why fail requires both magnitude AND gap

```python
fail = (target_sum_err > 0.10) and (target_sum_err - ref_sum_err > 0.05)
```

If both endpoints are slightly off in the same way, that's a model
property (the underlying weights mis-add long lists), not a fidelity
gap. We only fail when the target is *worse than the reference by a
meaningful margin* and *bad in absolute terms*.

---

## Cross-cutting design choices

### Why `DEFAULT_SCHEDULE_SEED = None` (random per run)

The schedule_seed controls the **order** in which (prompt, sample)
calls are issued — it does not affect the panel content (so it
doesn't break artifact comparability; the framework explicitly lists
schedule_seed as a stealth knob). With a constant seed across all
runs, a determined provider that hashes incoming prompts could see
the **exact same call sequence** every day and route those queries
to the genuine model. Randomizing per run defeats that. The seed
that was actually used is recorded in the artifact, so a run is
still individually reproducible.

### Why panel_id changes invalidate old artifacts

`assert_comparable()` refuses to compare two RunResults with
different `panel_id` or `prompt_hash`. That is on purpose: comparing
a run done against the v1 prompts to a run done against v2 prompts
would silently mix two different measurements. The `_v1` → `_v2`
bumps in this commit force any old artifacts to be re-run; that's
free since none have been collected yet.

### Why we don't have a logprob path yet

Every test in this suite has a documented "this would be much better
with logprobs" footnote. That requires:

- A `logprobs=True, top_logprobs=K` request flag wired through
  `client.py` and `Endpoint`.
- Per-provider knowledge of what they actually return (Anthropic
  returns nothing; OpenAI top-20; Together one token; AWS Bedrock
  none).
- A per-test logprob-path comparator (KL divergence for entropy,
  RUT or LT for arithmetic, etc.).

It's the highest-value follow-up but a separate engineering project.
Tracked in `THREATS.md`.

### Why no time-series / CUSUM yet

The current report is a point-in-time pass/fail. The Chen-Zaharia
"How is ChatGPT's behavior changing over time" paper showed
GPT-4's prime-checking accuracy drop from 97.6% to 2.4% between
March and June 2023 by exactly this kind of monitoring — but it
needs an aggregator that ingests artifacts into a time-series DB
and runs CUSUM/EWMA change-point detection. That's a separate
infrastructure concern outside the per-test design.

---

## Reading a comparator report

Each `compare_*()` function returns a dataclass. Common patterns:

- `*_gap_*` fields are always `reference - target` (or `target -
  reference` where the natural sign is opposite, e.g. error rates).
  Positive means the target is worse.
- `fail` is a boolean conclusion. The threshold(s) that produced it
  are also exposed (`fail_threshold_*_gt`, `curvature_gap_threshold`,
  etc.) so you can see the bar.
- `per_prompt` / `per_cell` lists let you drill into individual
  prompts when the aggregate fires.

When `fail = True`, the order of investigation is:

1. Check the **per-cell / per-prompt** breakdown for which specific
   items pushed the aggregate over.
2. Check the **secondary statistics** (modal accuracy when digit
   accuracy fired, mode-frequency, intra-side prefix means) to
   distinguish "weights changed" from "decoding noise changed."
3. Cross-reference with the other tests: an arithmetic+rollout fail
   together is a model swap; aggregation+single fail together is
   truncation; multi-needle alone with a curvature signal is
   KV-cache.
