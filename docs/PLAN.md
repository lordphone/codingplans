# Project plan

Snapshot 2026-10-24, from a planning conversation. Covers the project's aim,
competitors, the detection method, the calibration lab, a paper target, and
how all of that maps onto what is already in this repo.

## 1. What the project is

A watchdog for LLM coding plans. The core comparison is each provider's
flat-rate coding plan against **that same provider's** official pay-per-token
API: Moonshot's Kimi plan vs. Moonshot's API, Z.AI's GLM plan vs. Z.AI's API,
MiniMax, and possibly OpenCode Go as a reseller.

The suspicion is that plans may be cheaper to serve than advertised. Possible
causes:

- heavier quantization;
- a smaller model swapped in;
- caching that is off, or reported but not real;
- truncated context;
- quality drops at peak hours.

Goal: test both sides, measure the gap, and publish which plans match their API.

## 2. Competitors (as of Oct 2026)

- **Nobody found doing plan-vs-own-API.** Caching honesty (do reported cached
  tokens match real speedups?) looks completely unclaimed.
- **Artificial Analysis Endpoint Accuracy Index.** Closest work and biggest
  risk. It compares API endpoints for open-weights models against its own
  self-hosted copy of the official weights. Pay-per-token endpoints only: no
  plans, caching or time-of-day effects. They could add plans, so move fast.
- **Kimi Vendor Verifier** (Moonshot). Checks third-party hosts of Kimi, not
  Moonshot's own plan. Could be reused as one of our tests.
- **Drift trackers** (AI Stupid Level, IsItNerfed). Official APIs only.
- **OpenRouter.** Relies on providers' own quantization labels.
- **Price sites** (codingplan.org, coding-plan.org, awesome-coding-plan).
  Price and quota only; some run on affiliate fees. "codingplans" is nearly the
  same name as codingplan.org, so consider a name that signals "watchdog".

## 3. Method

The website only publishes results. The real work is the detection method.

1. **Calibration lab** on a local RTX 5090 (32 GB). Serve a smaller open model
   with vLLM or SGLang in each corner-cutting setup a provider might use, so
   the ground truth is known:
   - BF16 vs. FP8 vs. INT4 (AWQ/GPTQ);
   - prefix caching on vs. off;
   - context capped;
   - a smaller sibling model swapped in.
2. **Build detectors** and measure detection rate and false-alarm rate for each:
   - output fingerprints and statistical tests on output distributions (same
     prompts, fixed sampling) — how many queries for 95% confidence?
   - logprob shifts, where the API exposes logprobs;
   - cache timing: time-to-first-token on repeated vs. new prefixes, compared
     with reported cached tokens;
   - context cutoff: needle-in-a-haystack at growing lengths;
   - coding-task accuracy.
3. **Run the validated detectors** on real plans vs. APIs, repeatedly over
   weeks, including peak hours in China.

### Why the 5090, and its limits

- The providers' flagship models (hundreds of billions to ~1T parameters) will
  never fit on a 5090. That is fine: the 5090 validates the detection
  techniques, not the providers' models. Cache-timing, context and statistical
  tests depend little on which model runs.
- Quantization effects do not carry over perfectly. Large models often lose
  less quality from INT4, so detection can be harder at scale.
- Ways to close the gap:
  - use a small quantized MoE model (providers serve MoE models);
  - run each test across sizes in one family (e.g. 1.5B / 7B / 32B) and see
    how detection power changes;
  - rent 8× H100/H200 once for a final check on a large open model in BF16 vs.
    FP8 vs. INT4;
  - for plan-vs-API the question is "same or not", with calibration setting how
    big a gap counts.
- Needs Linux or WSL2, CUDA 12.8+, recent vLLM. Some data-center kernels may
  not run on consumer Blackwell.

**First step:** serve one ~7B model on the 5090 in BF16 and INT4, send both the
same ~200 prompts, and see whether we can tell them apart.

## 4. How this maps onto the repo

**Already built**

| Plan item | Where |
|---|---|
| Plan vs. official reference pairing | `benchmarks/endpoints.json` → `audits` groups |
| Output fingerprints | `benchmarks/fidelity/model_identity/` |
| Context cutoff | `benchmarks/fidelity/long_context/` (needle tests) |
| Cache honesty | `integrity/test_response_cache.py`, `integrity/test_token_accounting.py` |
| Coding accuracy | `benchmarks/fidelity/coding/` |
| Tool calls, reasoning budget | `agentic/`, `reasoning/` |
| False-alarm calibration (official vs. official) | `run_audit.py --calibrate` |
| Multiple-testing correction | Benjamini–Hochberg in the orchestrator |
| Related-work survey | `docs/research/cheating-vectors.md`, `docs/research/landscape.md` |

**Missing**

- **Positive ground truth.** `selftest.py` checks honest/cheating cases against
  a fake API only. Nothing measures detection rate against a real model in a
  known corner-cutting setup. That is the lab.
- **Lab wiring.** Runners are single-endpoint, so each local vLLM setup can be
  registered as an ordinary entry in `endpoints.json` (OpenAI-compatible base
  URL). The 5090 must sit in a Linux/WSL2 box, not the Mac.
- **Stronger detectors.** Cai et al. ("Are You Getting What You Pay For?",
  2504.04715) found classifiers and MMD near chance for FP8/INT8 vs. full
  precision on large models. A 7B BF16-vs-INT4 split should be easy, so the
  first experiment mainly validates the pipeline. The publishable result is how
  detection power falls with model size and milder quantization. RUT
  (rank-based uniformity test, 2506.06975) is a candidate detector to add.
- **Cache timing vs. ground truth.** No competitor covers caching honesty, and
  `test_response_cache.py` exists; checking it against prefix-cache on/off in
  the lab is cheap.

## 5. Paper

- The validated method is the contribution. It is publishable even if every
  plan turns out honest.
- Realistic target: a workshop paper in ~3–4 months. Later venues: IMC, FAccT,
  USENIX Security, COLM, NeurIPS Datasets & Benchmarks.
- Working title: *"Same Model, Different Plan: Auditing LLM Coding
  Subscriptions Against Their Own APIs."* Stay clear of the existing paper
  "Are You Getting What You Pay For?".
- Publish a public dataset and code.

## 6. Cautions

- Word results as measured differences, not "fraud". Publish the method
  openly. Plans may disclose some limits, such as a lower context cap.
- Never use free plans or credits from the audited providers: they would know
  those accounts and could serve them the full model. Test accounts should look
  like ordinary paying customers. Disclose who funds the work.
- Check each plan's terms of service (see `docs/REQUIREMENTS.md` §0). Some
  restrict use outside approved coding tools, and automated testing could get
  an account banned mid-study.

## 7. Funding

Possible source: a CMU professor (ML systems, the LLM Systems course
instructor, or CyLab). Budget ~$100–300/month for plans plus some cloud GPU
time.
