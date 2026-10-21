# How coding-plan providers can short-change customers, and how to detect it black-box

*Research report for the codingplans audit project. Compiled 2026-10-20. Scope: flat-rate "coding plans" (Kimi, Z.ai GLM, MiniMax, Alibaba Model Studio, Volcengine Ark, Xiaomi MiMo, Chutes, Synthetic.new, resellers) that expose OpenAI- or Anthropic-compatible endpoints, compared against each model's official pay-as-you-go API.*

> Caveat on sources: several 2026 arXiv papers below were read at abstract or partial-HTML level only. Numbers are quoted as their authors report them. Treat secondary write-ups (blogs, news) as leads, not evidence.

---

## 0. Executive summary

1. **The biggest real-world losses for coding customers come from the serving stack, not the weights.** Moonshot's K2 Vendor Verifier, Artificial Analysis's Endpoint Accuracy Index and OpenRouter's Exacto work all point the same way: tool-call parsing, output-token caps, reasoning caps, context limits and chat-template bugs cost more accuracy than FP8 quantization. Weight quantization exists, but the cheap ways to detect it are weak (Cai et al. 2025).
2. **Tool-calling fidelity is the top new test.** A K2VV-style suite measures trigger F1 against the official endpoint plus absolute schema validity. On Kimi K2 vendors it found schema accuracy ranging from 100% down to about 72%, and trigger behaviour off by up to 2x (Chutes made 3,657 tool calls against Moonshot's 1,958 on the same prompts).
3. **Cheap "configuration" probes catch a lot of cheating for almost nothing**: output caps, `max_tokens` handling, context-length truncation, reasoning-length distribution, hidden system-prompt injection (via the prompt-token offset), response caching (via a nonce), and sampling-parameter compliance. Each needs tens of calls, not thousands.
4. **For model substitution, add two 2026 methods**: KBF knowledge-boundary fingerprints (binomial test, about 100–700 probes, under $0.25 per audit, flagged 155/155 substitutions) and the cross-length tokenizer differential (zero-tolerance prompt-token deltas). Both complement the existing rollout-prefix and arithmetic tests. Use IRIS-style per-response "tell" counting to catch partial routing ("dilution").
5. **Statistics**: calibrate every threshold on reference-versus-reference runs, as KVV and Artificial Analysis do. Use Holm within a plan and Benjamini–Hochberg across the leaderboard. Report effect sizes with confidence intervals, and use equivalence tests (TOST) before calling a plan "at parity". Use anytime-valid or CUSUM monitoring for scheduled probes.

---

## 1. Landscape: who has measured this already

### 1.1 Moonshot K2 Vendor Verifier (K2VV) and Kimi Vendor Verifier (KVV)

**K2VV** ([GitHub](https://github.com/MoonshotAI/K2-Vendor-Verifier), [evalscope docs](https://evalscope.readthedocs.io/en/v1.13.0/benchmarks/k2_verifier.html))

- **Data:** about 4,000 real agentic requests with tool definitions. 50% of the set is published as a sample tarball. Each request is replayed against the vendor and against the official Moonshot API.
- **Parameters:** K2-thinking ran at temperature 1.0 with `max_tokens` 64,000; K2-0905 ran at temperature 0.6. Client defaults are concurrency 5, timeout 600 s and 3 retries, with an `--incremental` mode that re-runs only failures. For K2.5 with thinking off, it passes `chat_template_kwargs: {"thinking": false}` in the extra body.
- **Metric 1, ToolCall-Trigger Similarity (`tool_call_f1`).** Each request is classified against the official response:
  - TP: both return `finish_reason=="tool_calls"`.
  - FP: the vendor returns `tool_calls`, the official returns `stop`/other.
  - FN: the reverse of FP.
  - TN: neither returns `tool_calls`.
  - Precision, recall and F1 follow. This metric measures whether the vendor decides to call tools when the real model would.
- **Metric 2, ToolCall-Schema Accuracy.** `count_successful_tool_call / count_finish_reason_tool_calls`, where a call is successful if its arguments parse as JSON and validate against the declared JSON Schema. Raw counts are reported too.
- **Thresholds come from official-vs-official variance.** Moonshot ran its own API several times.
  - K2-thinking: minimum F1 75.81%, mean 76%, so the pass bar is 73%.
  - K2-0905: minimum 82.71%, mean 84%, so the pass bar is 80%.
  - This calibration step is the methodological core and we should copy it.
- **Selected results.**
  - K2-0905 schema accuracy: Moonshot, DeepInfra, Fireworks, Infinigence and NovitaAI scored 100%. vLLM scored 76.0%, SGLang 73.1%, Volc (Volcengine) 72.9%, Baseten 72.5%, AtlasCloud 72.4% and Together 72.0%.
  - K2-0905 trigger F1: Groq 69.5% and Nebius 50.6%, both below the 80% bar.
  - K2-thinking: Chutes F1 68.1%, with 3,657 `tool_calls` finishes against the official 1,958.
- **Root causes Moonshot identifies.**
  - Missing guided or constrained decoding. The official API uses an "Enforcer".
  - Outdated vLLM/SGLang builds.
  - Malformed historical tool-call IDs. K2 expects `functions.func_name:idx`, and the official API normalizes IDs before inference.

**vLLM debugging case study** ([vLLM blog](https://vllm.ai/blog/2025-10-28-kimi-k2-accuracy)). This explains why honest-looking vendors fail. The three bugs it found:
1. `add_generation_prompt` was silently dropped, so requests ended with `finish_reason: stop` instead of `tool_calls`. Before the fix there were 218 successful calls against 1,286 official.
2. Empty `content: ''` was converted to a list and rendered literally into the prompt.
3. A strict tool-call-ID parser threw away valid calls.

After the fixes, F1 was 83.6% and schema accuracy 76%. The model still sometimes called undeclared tools, which constrained decoding prevents.

**KVV, the successor** ([Kimi blog](https://www.kimi.ai/blog/kimi-vendor-verifier), [GitHub](https://github.com/MoonshotAI/Kimi-Vendor-Verifier); [GIGAZINE](https://gigazine.net/gsc_news/en/20260421-kimi-vendor-verifier/)). KVV is a staged pipeline:

1. **Pre-verification (`tests/params/`).** Checks that the API enforces fixed sampling parameters (`temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, `n`). Moonshot enforces T=1.0 and top_p=0.95 in thinking mode because "many benchmark anomalies came from misuse of decoding parameters". Formal benchmarks run only after these tests pass.
2. **`tests/tool_call_json_schema/`.** Each schema from a valid-schema corpus is sent as tool parameters, a call is forced, and the arguments are validated locally with `jsonschema`. Every case runs streaming and non-streaming.
3. **`tests/k3_features/`.** Covers dynamic tools, `response_format`, `tool_choice` and thinking effort.
4. **`tests/prompt_tokens/`.** Compares streamed `usage.prompt_tokens` with expected constants. This is a token-accounting and template-integrity check.
5. **Benchmarks.**
   - OCRBench (about 5-minute smoke test) and MMMU-Pro (vision preprocessing).
   - AIME2025 avg@32 at 98k max tokens. It is described as a long-output stress test that catches KV-cache bugs and quantization degradation that short benchmarks miss.
   - K2VV ToolCall.
   - SWE-Bench / DeepSWE, using a sandbox.
   - For K3: BEAM 1M-token long-memory.
6. **Results (K3 leaderboard).** Moonshot DeepSWE 0.675, vendors 0.658–0.695; BEAM 0.29–0.32.
7. **Cost.** The full pipeline takes about 15 h on two 8×H20 servers. Moonshot says it is "seeking lighter agentic tests". Our project can fill that gap.

### 1.2 Artificial Analysis Endpoint Accuracy Index (Aug 2026)

Sources: [methodology](https://artificialanalysis.ai/methodology/endpoint-accuracy-index), [launch article](https://artificialanalysis.ai/articles/endpoint-accuracy-index).

- **Design.** Each provider endpoint is scored as a percentage of AA's self-hosted reference deployment of the official weights. The composite weights three suites equally:
  - BFCL v4-500 (tool calling, 3 repeats, weighted toward multi-turn and parallel categories).
  - HLE-250 (10 repeats).
  - AA-LCR-25 (long context, 10 repeats).
- **Parity rule.** An endpoint is at parity if its score falls inside the reference's 95% CI.
- **Settings.** Highest reasoning mode, the endpoint's maximum output and context, and `tool_choice=auto` with strict schemas where supported.
- **Findings.**
  - GLM-5.2: restrictive output-token limits cut off reasoning. The worst endpoints score half the reference or less on HLE.
  - gpt-oss-120b: some endpoints score 22% on BFCL against the reference's 37%. Some produce far fewer reasoning tokens at the same configured effort. Restricted context windows truncate long-context tasks.
  - Low scorers emit roughly half the reference's output tokens per task.
- **Lesson.** Output-token count per task is a cheap proxy for reasoning or output truncation.
- **Earlier work.** The 2025 gpt-oss-120b AIME×32 comparison found spreads from 93.3% (most vLLM-based providers) down to 80% (Azure) and 36.7% (CompactifAI) ([Simon Willison](https://feeds.simonwillison.net/2025/Aug/15/inconsistent-performance/), [ndurner](https://ndurner.substack.com/p/ai-inference-provider-inconsistencies)).

### 1.3 OpenRouter Exacto

Source: [blog](https://openrouter.ai/blog/announcements/provider-variance-introducing-exacto/).

- **Telemetry.** On every tool-call response OpenRouter checks:
  1. Whether the arguments are valid JSON.
  2. Whether the tool name is among those supplied.
  3. Whether the arguments match the schema.
- **Metrics.** "Accuracy" is the share of calls passing those checks. "Propensity" is how often a model calls tools when tools are offered, compared across providers of the same model. Comparisons are made within an app to control for workload.
- **Quantization claim.** OpenRouter says it has seen no measurable tool-call impact from quantization alone (DeepInfra fp4 on DeepSeek 3.1 stayed competitive). It attributes problems mostly to tool-call parsers and inference engines. The [GreaterWrong critique](https://www.greaterwrong.com/posts/KsyoSAyBRXtwzSugg/not-pinning-your-openrouter-provider-might-invalidate-your) counters that compressed models can behave differently even when accuracy is similar.

### 1.4 Academic auditing work, 2024–2026

| Work | Signal | Access | Key result |
|---|---|---|---|
| **Model Equality Testing (MET)**, Gao, Liang & Guestrin, ICLR 2025 ([2410.20247](https://arxiv.org/abs/2410.20247)) | MMD two-sample test with a string (Hamming) kernel on sampled completions | text + reference samples | Median power 77.4% at about 10 samples/prompt. **11/31 Llama endpoints** (Summer 2024) differed from the reference weights. |
| **Cai et al., "Are You Getting What You Pay For?"** ([2504.04715](https://arxiv.org/html/2504.04715v1)) | Text classifiers, identity prompting, MMD, benchmarks, logprobs, TEE | various | **Negative results:** BERT/T5/LLM2Vec classifiers stay at about 50% on FP8 or INT8 vs full precision. Identity prompting fails (under 5% on technical details). MMD power is near α for large models and breaks down at 20% random mixing. Benchmarks hide FP8. Logprobs are noisy across vLLM/HF and H100/A100. Recommends TEEs (about 3–16% overhead). |
| **RUT**, rank-based uniformity test ([2506.06975](https://arxiv.org/abs/2506.06975)) | Rank of a test statistic vs a local reference model; uniform under H0 | text + local model | Higher power than MMD under small budgets. Covers quantization, fine-tuning, jailbreaks and substitution. Query patterns look natural, which resists evasion. |
| **Idiosyncrasies in LLMs**, Sun et al., ICML 2025 ([2502.12150](https://arxiv.org/abs/2502.12150)) | Fine-tuned embedding classifier | text | 97.1% on 5-way frontier models. Only 59.8% across 4 Qwen2.5 sizes (85.5% binary). 96.8% base vs instruct. Good for cross-family swaps, weak for same-family or quantized. |
| **Log Probability Tracking**, Chauvin et al., ICLR 2026 ([2512.03816](https://arxiv.org/abs/2512.03816)) | Mean logprob of a single output token; simple test | logprobs | About 1000× cheaper than prior methods. Detects a single fine-tuning step. Introduces the TinyChange benchmark. |
| **B3IT**, Token-Efficient Change Detection, Chauvin et al., ICML 2026 ([2602.11083](https://arxiv.org/abs/2602.11083), [code](https://github.com/timothee-chauvin/token-efficient-change-detection-llm-apis)) | "Border inputs": prompts where the top-1 next token is a near-tie. Find them by querying 3× at low temperature, then watch whether the support of the first output token changes. | **text only** | 30× cheaper than prior work. Ran on 93 endpoints (64 models, 20 providers). Border inputs found on most **non-reasoning** endpoints. |
| **KBF**, Knowledge Boundary as Fingerprint ([2605.29524](https://arxiv.org/html/2605.29524v2)) | Numeric facts near the model's knowledge boundary, stable under benign configs; binomial test on mismatches vs a Clopper–Pearson-calibrated null rate | text only, stored reference | **155/155** substitutions flagged across 16 production endpoints, 0/16 false positives, 0/30 FP under wrapper configs. N = 109–681 probes. **About $0.24 per audit.** Catches mixed routing below 7% for budget substitutes. 7/28 shadow-API endpoints were inconsistent. |
| **IRIS** ([2607.20860](https://arxiv.org/html/2607.20860v1)) | Random-generation probes (coin flips, digits, bit strings) → 179-dim formatting/run-statistics features → classifier posterior; tells counted for dilution | text only | AUROC 0.99 across a six-size Qwen3 ladder. Dilution ε=5/10/20/40% detected in about 64/32/16/8 queries (diagnostic). Estimator ε̂ = (f̂−α₁)/(q−α₁). Live audit flagged 14/15 same-model provider pairs. |
| **AgentProv** ([2609.00052](https://arxiv.org/abs/2609.00052)) | Categorical **tool-call policy** distribution + MMD permutation test | text/tool calls | 100% detection on 630 checkpoint pairs. **FPR under provider system-prompt injection: 7%**, against 67% for MET and 53% for RUT. Text-based audits wrongly accuse providers that inject system prompts. Disagreements traced to a **token-count side channel that reveals injected system prompts**. |
| **Four-stage identity protocol** ([2608.31142](https://arxiv.org/html/2608.31142v1)) | Config fingerprint (context/max output) → **cross-length tokenizer differential** (prompt_tokens delta must be constant across ≥3 lengths incl. long CJK and English, zero tolerance) → behavioural corroboration | text + usage | Identified an anonymous model as the GLM-5.3 line (constant 75-token delta). About 100 calls. Self-identification and style failed. A usage-forging proxy can fake Stage 2, so behaviour must corroborate. |
| **Shadow APIs** ([2603.01919](https://arxiv.org/abs/2603.01919)) | Utility, safety and fingerprint audit of resellers | text | 45.83% of fingerprint tests failed identity verification. Performance divergence up to 47.21%. |
| **Token-billing audits**: "Invisible Tokens, Visible Bills" ([2505.18471](https://arxiv.org/html/2505.18471v1)), CoIn, PALACE ([2508.00912](https://arxiv.org/html/2508.00912v1)), "Token Inflation" ([2605.30040](https://www.emergentmind.com/papers/2605.30040)) | Hidden reasoning-token count prediction and consistency checks | usage | Formalize token-count, call-count and model-call inflation. PALACE predicts hidden reasoning-token counts from (prompt, answer) pairs. |
| **Prompt-cache timing audit**, Gu et al. ([2502.07776](https://arxiv.org/abs/2502.07776)) | TTFT distribution, cache-hit vs cache-miss, hypothesis test | timing | Detected **cross-user** cache sharing at 7 providers. |
| **TOPLOC** ([2501.16007](https://arxiv.org/html/2501.16007v2)) | LSH of activations, provider-side proofs | needs provider cooperation | Detects model, prompt or precision changes with 100% accuracy in the authors' experiments. Worth naming as the "ask" to plans, but not black-box. |

**Synthesis.** Text-only substitution detection works well **across families and sizes** (KBF, IRIS, idiosyncrasy classifiers, our rollout-prefix test). It works poorly for **FP8 or mild INT8** (Cai et al.). For quantization, the strongest black-box signals are:
- precise computation (our per-digit multiplication test);
- long-output stress, where AIME-style or long-generation errors compound (KVV's rationale);
- logprobs when exposed (LPT);
- near-tie token flips at low temperature (B3IT).

Hidden system prompts are a serious **false-positive confound** for every text-distribution test (AgentProv). Always run the prompt-token side channel first.

### 1.5 Real-world reports and incidents

- **Z.ai GLM-5 coding plans (March 2026).** r/ZaiGLM threads such as "Don't buy GLM coding plans" report thinking that "feels artificially shortened", output resembling a quantized model, and degradation beyond 80–100k tokens of context. This followed "infrastructure changes" and a compute shortage in late February 2026 that restricted signups ([Efficienist](https://efficienist.com/users-report-declining-quality-on-z-ais-glm-5-coding-plans/), [Wikipedia: Z.ai](https://en.wikipedia.org/wiki/Z.ai)). These are anecdotal, but they map directly onto tests in §2.3 (reasoning budget) and §2.2 (long-context).
- **Quota opacity.**
  - The GLM Coding Plan advertises "prompts per 5 h" (older docs: 80/400/1,600; newer: 120/600/2,400) plus weekly caps, with "one prompt ≈ 15–20 model calls" ([docs.z.ai](https://docs.z.ai/devpack/overview), [FAQ](https://docs.z.ai/devpack/faq)). The unit customers can measure (HTTP requests or tokens) is not the advertised unit.
  - Kimi returns 403 for the 5-hour cap and 429 for rate limits, sometimes with a misleading "engine overloaded" message ([Kimi error reference](https://www.kimi.com/code/docs/en/kimi-code/error-reference.html), [pawwork #740](https://github.com/Astro-Han/pawwork/issues/740)).
  - Alibaba distinguishes per-minute "usage allocated quota exceeded" from "hour allocated quota exceeded" (the 5-hour window). Transient throttling shows up as `insufficient_quota` ([Alibaba error codes](https://www.alibabacloud.com/help/en/model-studio/error-code), [Coding Plan FAQ](https://www.alibabacloud.com/help/en/model-studio/coding-plan-faq), [pi #10656](https://github.com/earendil-works/pi/issues/10656)).
- **First-party incidents show that degradation can be unintentional and look like cheating.**
  - Anthropic, Sept 2025 postmortem ([link](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)): a context-window routing bug hit 16% of Sonnet 4 requests at peak; a TPU misconfiguration produced stray Thai and Chinese characters; a top-k compiler bug.
  - Anthropic, April 2026 Claude Code postmortem ([InfoQ](https://infoq.com/news/2026/05/anthropic-claude-code-postmortem), [The Register](https://www.theregister.com/2026/04/23/anthropic_says_it_has_fixed/)): default reasoning effort was lowered from high to medium; a thinking-pruning bug caused cache misses every turn and drained rate limits; a verbosity system-prompt change reportedly cut median visible thinking from about 2,200 to about 600 chars.
  - **Each of these is a vector in §2, and each would have been caught by a cheap scheduled probe.**
- **Chinese relay ("中转站") ecosystem.** Community guides list common dilution tricks: routing claude-opus requests to cheaper models, domestic models returning `model: claude-opus`, context or multimodal limits behind an HTTP 200. Tools named include LLMprobe-engine (87 probes), Claude Detector (19 probes) and cc-proxy-detector ([CSDN guide](https://aicoding.csdn.net/6a44780010ee7a33f285443e.html), [CSDN comparison](https://aicoding.csdn.net/6a6873d6662f9a54cb952e4e.html), [apito](https://apito.ai/zh/blog/getting-started/how-to-verify-claude-api-authenticity-fingerprint-detection/)). Most are vendor marketing, and many rely on identity self-report, which is unreliable.

---

## 2. Catalogue of short-changing vectors and detection methods

Format for each vector: **Why** (the provider's incentive) / **Detect** / **Metric & statistic** / **N** (sample size) / **Confounds** / **Ref?** (absolute, or needs the official endpoint) / **Cost** / **Cites**.

Impact (I) and Detectability (D) are each rated 1–5. Priority = I×D.

### 2.1 Tool-calling degradation (I=5, D=5, priority 25)

**Why.** Constrained decoding costs throughput. Vendors run cheaper or older vLLM/SGLang builds with lax parsers, skip the official "enforcer", mis-render chat templates, or drop parallel calls. Some of this is negligence rather than fraud, but the customer impact on agent loops is the same.

**Detect: K2VV/AgentProv-style suite, "TCF" (tool-call fidelity).**
- **Panel.** 150–300 prompts drawn from coding-agent shapes (mirrors of Claude Code tools: `Read`, `Edit`, `Bash`, `Grep`, `Write`, `TodoWrite`). Include:
  - (a) single-call-obvious prompts;
  - (b) ambiguous prompts where calling or not calling both happen (to measure the trigger distribution);
  - (c) prompts that should produce **parallel** calls ("read these 3 files");
  - (d) **nested schemas** with enums, `required`, arrays of objects, `additionalProperties:false`, integer bounds and string patterns;
  - (e) multi-turn prompts with prior `tool` results, including Kimi-style IDs and a few malformed historical IDs;
  - (f) `tool_choice` = `auto` / `required` / `{"type":"function","name":...}` / `none`;
  - (g) a large tool list (40+ tools, as in a Claude Code session) to test whether long tool lists are truncated;
  - (h) arguments that embed code containing quotes, newlines, backslashes, unicode and `</` sequences, to test escaping.
- Run every case **streaming and non-streaming**. Reassemble the streamed deltas and check `index` handling for parallel calls. If the plan offers it, also run through the **Anthropic-compatible** endpoint (`tool_use` blocks, `stop_reason: tool_use`), since Claude Code uses that path.

**Metrics.**
- **Absolute (no reference needed):**
  - JSON parse rate.
  - Schema-valid rate (`jsonschema`).
  - Rate of calls to undeclared tool names.
  - `tool_choice` compliance (`required` must call; named must call that name; `none` must not call).
  - Raw tool-call markup leaked into `content` (for example `<|tool_call_begin|>`, `<tool_call>`, `functions.` prefixes). This is a parser-failure signature.
  - Streaming/non-streaming consistency.
  - For deterministic prompts with ground truth (e.g. "edit line 12 of foo.py to X"), exact match on argument values.
- **Relative to the official endpoint:**
  - K2VV trigger F1 on `finish_reason`.
  - Propensity ratio (tool-call rate, plan vs official).
  - Parallel-call count distribution, compared with a chi-square or Fisher test.
  - Optionally, AgentProv's MMD on the categorical tool-choice distribution.

**Statistics.**
- Schema-valid rate: compare with a two-proportion or Fisher exact test, or treat as absolute with a one-sided binomial test against the official rate. Official endpoints with constrained decoding typically score 100%.
- Distinguishing 100% from 98% needs about 150–400 tool calls, depending on how close to 100% the reference is (see §4).
- Trigger F1: calibrate the threshold by running **official vs official twice** (KVV's method) and set the bar at the minimum, or at the reference's 2.5th percentile from a bootstrap.

**N.** 200 prompts × 2 (stream/non-stream) at the vendor-recommended temperature, i.e. 400 calls per endpoint. The reference run is reusable across plans.

**Confounds.**
- Temperature: use the official recommended setting, and record it if the plan forces its own.
- Tool-call propensity drifts with the system prompt, so use none or a fixed one.
- Reasoning models may emit text before tool calls.
- The Anthropic↔OpenAI translation layer may be the culprit rather than the model. Report it either way: the customer impact is real.

**Ref?** Hybrid. Schema validity is absolute; F1 and propensity need the reference.

**Cost.** About 400 calls per plan per model plus about 800 for the reference (official ×2 for calibration). Mostly short outputs.

**Cites.** [K2VV](https://github.com/MoonshotAI/K2-Vendor-Verifier), [KVV](https://github.com/MoonshotAI/Kimi-Vendor-Verifier), [vLLM K2 debugging](https://vllm.ai/blog/2025-10-28-kimi-k2-accuracy), [OpenRouter Exacto](https://openrouter.ai/blog/announcements/provider-variance-introducing-exacto/), [AA EAI (BFCL)](https://artificialanalysis.ai/methodology/endpoint-accuracy-index), [AgentProv](https://arxiv.org/abs/2609.00052).

### 2.2 Output-length caps, `max_tokens` handling, and silent context truncation (I=5, D=5, priority 25)

**Why.** Long outputs and long contexts dominate serving cost (KV-cache memory). A plan may advertise 200k context / 128k output while capping at 32k/8k, or serve a smaller context window via a cheaper configuration and silently drop history (middle-out or head truncation) instead of returning an error. AA identifies output caps and context limits as primary failure modes, and GLM-5 users report degradation beyond 80–100k tokens.

**Detect, in four probes:**

1. **Output-cap probe (absolute).**
   - Prompt: "Output the integers from 1 to 40000, one per line, nothing else." Use a deterministic sequence with a known token cost per line, measured with a local tokenizer. Set `max_tokens` = the advertised max output.
   - Record `finish_reason`, `usage.completion_tokens`, the last integer emitted, and whether the stream ended without a `[DONE]` or finish chunk.
   - A cap shows as `finish_reason=length` at a round number well below the advertised maximum, or as `stop` while the sequence is incomplete (a silent cut).
   - Binary-search the cap with about 6 calls.
   - Confound: the model may stop early on its own. Mitigate with a sequence format the model reliably continues, and compare with the official endpoint.

2. **`max_tokens` respect.** Set `max_tokens=16` on an essay prompt and assert `completion_tokens ≤ 16`, `finish_reason=length` and the visible text length agrees. Also send `max_tokens` above the advertised cap and check for a clear error rather than silent clamping. For reasoning models, record whether reasoning tokens count toward `max_tokens`, as the official API documents. 3 calls.

3. **Context-capacity probe (absolute + reference).**
   - Construct prompts at 25/50/75/90/98% of the advertised context with a filler of known local token count. Place **canaries at the head, middle and tail**, e.g. `CANARY-HEAD=<random 8 hex>`.
   - Ask the model to return all three canaries. Also compare `usage.prompt_tokens` against the local tokenizer count (see §2.6).
   - Truncation signatures:
     - prompt_tokens comes back lower than the local count (the provider truncated before inference);
     - the head canary is lost while the tail survives (left truncation);
     - the middle canary is lost (middle-out);
     - success at 50% but failure at 75% or more (an effective window smaller than advertised).
   - Extends the existing needle tests, which measure retrieval quality rather than the hard limit.
   - About 15 calls per length sweep, but expensive in input tokens (5 lengths × 3 repeats at up to 200k tokens is roughly 1.5–2M input tokens). It runs within a flat plan's quota, though it consumes it.

4. **Multi-turn history and reasoning pass-back integrity.**
   - Run a 6-turn conversation in which turn 1 contains a fact (inside a tool result) and turn 6 asks for it, with long filler in between.
   - Also check whether the plan honours `reasoning_content` pass-back (interleaved thinking) when the official API expects it. KVV notes thinking content "must be passed back correctly".
   - Compare against the official endpoint.

**Metric.** Hard cap values (point estimates) and canary recall per position per length, which is binary and summarized with Wilson CIs.

**N.** About 3 repeats per length suffice because the failure is usually deterministic.

**Ref?** Mostly absolute against advertised numbers. Use the reference only to rule out a model-intrinsic failure.

**Cites.** [AA EAI article](https://artificialanalysis.ai/articles/endpoint-accuracy-index), [Efficienist](https://efficienist.com/users-report-declining-quality-on-z-ais-glm-5-coding-plans/), [four-stage protocol Stage 0/1](https://arxiv.org/html/2608.31142v1), [OpenRouter middle-out transform](https://openrouter.ai/docs/features/message-transforms), [Anthropic Sept 2025 postmortem](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues).

### 2.3 Reasoning or thinking budget reduction (I=5, D=4, priority 20)

**Why.** Reasoning tokens make up most of the output on hard coding tasks, so on a flat plan they are pure cost. Ways to cut them:
- force `thinking` off or a low effort level;
- cap `budget_tokens`;
- inject a "be concise" instruction;
- truncate reasoning and force an answer.

Real precedents: AA found some gpt-oss endpoints produce "far fewer reasoning tokens at the same configured level"; GLM-5 users complain of shortened thinking; Anthropic itself lowered the default effort in Claude Code.

**Detect: Reasoning-Length Distribution (RLD) test.**
- **Panel.** 40–60 problems with verifiable answers that **need** non-trivial reasoning (e.g. multi-step arithmetic or logic, small algorithmic puzzles with exact outputs, mid-difficulty AIME-style items). Reasoning length on these varies, but its distribution is stable for a given model.
- **Per response, record:**
  - `usage.completion_tokens_details.reasoning_tokens`, if present;
  - the token length of `reasoning_content` / `thinking` blocks under the local tokenizer;
  - visible answer length;
  - correctness;
  - `finish_reason`;
  - whether the reasoning ends abruptly (no concluding sentence, or a `</think>` injected mid-word).
- **Effort-response check.** Run the same panel at each advertised effort level (low/medium/high, or `budget_tokens` 2k/16k). An honest endpoint's reasoning length should **increase monotonically** with effort. A flat profile means the parameter is ignored.

**Statistic.**
- Paired per-prompt log-ratio of reasoning length (plan vs official). Use a Wilcoxon signed-rank test with the median ratio and a bootstrap CI as effect size.
- Two-sided at the panel level, plus a pre-registered one-sided "reduction" hypothesis.
- Also run McNemar on per-prompt correctness.
- With k=3 samples per prompt and 50 prompts (150 calls), a 30% median reduction is detectable with high power. Reasoning-length CV within a prompt is typically 0.3–0.6 on a log scale. Calibrate with official-vs-official runs.
- Also report **reported vs observed reasoning tokens**: `reasoning_tokens` minus the locally counted length of `reasoning_content`. A large positive gap means billed but unseen reasoning, which is the CoIn/PALACE concern.

**Confounds.**
- Sampling temperature: use the vendor-recommended setting on both endpoints.
- Some APIs summarize thinking rather than returning it raw, so compare `reasoning_tokens` rather than text in that case.
- Reasoning length legitimately varies with chat-template differences.

**Ref?** Requires the reference, except the effort-monotonicity check, which is absolute.

**Cost.** About 150 calls per endpoint per effort level, with long outputs (2–20k tokens each).

**Cites.** [AA EAI](https://artificialanalysis.ai/articles/endpoint-accuracy-index), [Efficienist](https://efficienist.com/users-report-declining-quality-on-z-ais-glm-5-coding-plans/), [Anthropic April 2026 postmortem coverage](https://infoq.com/news/2026/05/anthropic-claude-code-postmortem), [KVV (thinking effort tests; enforced T/top_p in thinking mode)](https://github.com/MoonshotAI/Kimi-Vendor-Verifier), [PALACE](https://arxiv.org/html/2508.00912v1), [Invisible Tokens](https://arxiv.org/html/2505.18471v1).

### 2.4 Model substitution and aliasing: smaller, distilled, older model or different checkpoint (I=5, D=4, priority 20)

**Why.** The largest margin available to a provider is serving "glm-5" as glm-4.x or a "-flash"/"-air" variant, serving K2 as an older checkpoint, or routing a fraction of traffic to a cheaper model at peak ("dilution").

**Already covered in the repo:** the T=0 rollout prefix, first-word entropy and arithmetic tests.

**Detect, adding three complementary methods:**

1. **KBF knowledge-boundary probes (absolute after a one-time enrolment).**
   - **Enrolment.** Generate about 300–700 numeric-fact probes near the model's knowledge boundary (15 domains, e.g. melting points, OEIS terms, astronomy values, library version or release numbers) from the **official** endpoint. Keep probes that are stable across repeats and benign configs, and drop those a smaller sibling answers the same way (contrastive screening).
   - **Calibration.** Run the official endpoint again to estimate the null mismatch rate p₀ with a one-sided Clopper–Pearson upper bound (γ=0.99).
   - **Test.** Send each probe once to the plan and count k mismatches. p = P(Bin(N, p₀) ≥ k); flag if p < α.
   - **Cost.** About 100–700 short calls (KBF reports under $0.25 per audit). Catches budget substitutes below 7% routing.
   - Maintain a panel version (`KBF_PANEL_v1`) per this repo's panel-versioning rule.
   - **Confound:** a hidden system prompt or different temperature could shift answers, but KBF reports 0/30 false positives under wrapper configs.

2. **Cross-length tokenizer differential (absolute or relative, nearly free).**
   - Send 4–6 prompts of increasing length (short and long, English and CJK, plus code) to both the plan and the official endpoint, with `max_tokens=1`.
   - Compute Δ = plan.prompt_tokens − official.prompt_tokens. **Same tokenizer and template ⇒ Δ is constant (often 0) across lengths.** A length-dependent Δ ⇒ different tokenizer ⇒ different model family or version.
   - A constant non-zero Δ means a different chat template or an **injected system prompt** (see §2.6).
   - Compare with a local Hugging Face tokenizer plus chat template for an absolute check.
   - About 10 calls with zero tolerance.
   - **Confound:** a usage-forging proxy can fake counts, so corroborate with behaviour.

3. **Per-response dilution tells (IRIS-style).**
   - Probes: random-generation prompts ("flip 30 coins, output H/T", "20 random digits") at T=1.
   - Featurize each response (run lengths, symbol frequencies, formatting). Train a lightweight classifier (logistic regression or GBM) on official vs known-cheaper-sibling outputs. Count per-response "tells" where the score exceeds a threshold calibrated so the honest tell rate is α₁ ≈ 1–2%.
   - Test with a one-sided binomial on tell count vs α₁. Estimate the routed fraction as ε̂ = (f̂−α₁)/(q−α₁).
   - Budget for a target dilution ε: m ≈ ln(1/δ)/(ε·q). For ε=10% and q=0.5, about 60–100 calls.
   - This converts our existing whole-run tests into a **mixture-aware** test. **Spread probes over the day**, because dilution is likely peak-only.

4. **B3IT border inputs (cheap change monitoring, non-reasoning modes only).**
   - Discover prompts where the T≈0 first token flips between two or more candidates on the official endpoint (3 queries each).
   - Monitor whether the plan's first-token support set matches.
   - Very cheap: 1 output token per call.
   - Best for "did the model behind the plan change since last week?" rather than "is it the official model?". Different hardware or kernels can shift near-ties, so use it as a change detector against the plan's own baseline.

5. **Identity self-report: do NOT use as evidence.**
   - Cai et al. found under 5% accuracy on technical details. The four-stage protocol saw 300 probes yield zero credible self-identifications, and identity answers flip with serving-layer policy.
   - Record the `model` field and `system_fingerprint` (as metadata only), and record identity answers only as weak corroboration.
   - **Knowledge-cutoff probes** (dated events, library releases; cf. LLMLagBench cited in IRIS) are somewhat better, as a cheap way to separate old from new checkpoints.

**Ref?** KBF needs a one-time official enrolment. Tokenizer differential is absolute with a local tokenizer. IRIS needs reference plus suspected-substitute samples for training.

**Cites.** [KBF](https://arxiv.org/html/2605.29524v2), [four-stage protocol](https://arxiv.org/html/2608.31142v1), [IRIS](https://arxiv.org/html/2607.20860v1), [B3IT](https://arxiv.org/abs/2602.11083), [MET](https://arxiv.org/abs/2410.20247), [RUT](https://arxiv.org/abs/2506.06975), [Idiosyncrasies](https://arxiv.org/abs/2502.12150), [Cai et al.](https://arxiv.org/html/2504.04715v1), [Shadow APIs](https://arxiv.org/abs/2603.01919).

### 2.5 Weight or KV-cache quantization (aggressive INT4/FP4, quantized KV cache) (I=4, D=3, priority 12)

**Why.** It saves 2–4× memory and boosts throughput. FP8 is usually benign (OpenRouter, Cai et al.). INT4/FP4, quantized KV cache and aggressive pruning degrade long or precise generation.

**Already covered:** per-digit multiplication and long-context needles (the latter covers KV-cache quantization).

**Improvements:**
- **Long-output compounding test**, following KVV's AIME rationale. Use tasks whose correctness depends on a long chain of exact steps:
  - multi-digit long division written out;
  - "simulate this 60-step stack machine" with an exact final state;
  - write a 300-line program that must pass tests.
  Error probability grows with length under quantization noise. Fit accuracy vs chain length (logistic regression with an endpoint×length interaction) and test the interaction term. It is more sensitive than a single-length accuracy comparison.
- **Logprob tests when the plan exposes `logprobs`.**
  - LPT: request 1 token with `top_logprobs=20` on a fixed panel and compare the mean logprob of the argmax token with the reference using a t-test or permutation test across prompts.
  - RUT: rank of the official-model statistic.
  - Many coding plans do not expose logprobs, so record "logprobs unsupported" as a transparency finding.
- **Paired near-tie flip rate (B3IT)** at T≈0 vs the official endpoint on border inputs. Quantization shifts near-ties systematically, though hardware nondeterminism does too. Calibrate with official-vs-official runs at different times.

**Confounds.** Batch-size nondeterminism and GPU type (Cai et al. found logprob differences across vLLM/HF and H100/A100). Never treat any single-token exact mismatch as evidence. Use distributional tests calibrated on reference repeat runs.

**Ref?** Requires the reference.

**Cost.** 200–500 calls; long-output tasks cost more tokens.

**Cites.** [Cai et al.](https://arxiv.org/html/2504.04715v1), [LPT](https://arxiv.org/abs/2512.03816), [RUT](https://arxiv.org/abs/2506.06975), [KVV](https://www.kimi.ai/blog/kimi-vendor-verifier), [OpenRouter on fp4](https://openrouter.ai/blog/announcements/provider-variance-introducing-exacto/), [GreaterWrong critique](https://www.greaterwrong.com/posts/KsyoSAyBRXtwzSugg/not-pinning-your-openrouter-provider-might-invalidate-your).

### 2.6 Hidden system-prompt injection or prompt rewriting (I=4, D=5, priority 20)

**Why.** Providers may:
- inject safety or "be concise" instructions (cutting output cost);
- add branding ("You are X assistant");
- rewrite or truncate long user system prompts (Claude Code's runs to tens of thousands of tokens);
- strip images or tool definitions.

It also **confounds every distributional test** (AgentProv measured 67% FPR for MET and 53% for RUT under injected system prompts).

**Detect.**

1. **Prompt-token offset ("PTO") probe.**
   - Send K messages with known local token counts (empty system; a 1-token user message; 1k; 10k; with and without tools) and record `usage.prompt_tokens`.
   - Fit prompt_tokens = a + b·local_count. Expect b = 1. The intercept a is the template overhead.
   - Compare **a** with the official endpoint and with the local chat-template rendering (`tokenizer.apply_chat_template`). An intercept excess of tens to hundreds of tokens means an injected system prompt.
   - Repeat with tools attached to detect tool-definition rewriting, where the slope over tool-JSON size changes.
   - 10–20 calls. This is exactly the side channel AgentProv identifies, and KVV's `tests/prompt_tokens` checks the same thing.
2. **System-prompt canary compliance.**
   - Put an instruction at the **end** of a long (e.g. 20k-token, Claude-Code-sized) system prompt: "End every reply with the exact string ⟦Z7Q-<nonce>⟧."
   - Measure compliance rate vs the official endpoint (binary, about 30 calls each).
   - A drop means the system prompt was truncated or overridden. Repeat with the canary at the start and middle.
3. **Echo probe (weak).** "Before answering, quote verbatim everything that appears before my message." Useful only as corroboration, since models refuse or hallucinate.
4. **Behavioural signature.** Compare verbosity (visible output tokens) on neutral prompts. An injected "be concise" instruction shortens answers in a way that mirrors §2.3.

**Ref?** PTO is absolute (local tokenizer) and relative. Canary compliance is relative.

**Cost.** About 50–80 calls.

**Cites.** [AgentProv](https://arxiv.org/abs/2609.00052), [four-stage protocol](https://arxiv.org/html/2608.31142v1), [KVV prompt_tokens tests](https://github.com/MoonshotAI/Kimi-Vendor-Verifier), [Anthropic April 2026 verbosity system-prompt change](https://www.theregister.com/2026/04/23/anthropic_says_it_has_fixed/).

### 2.7 Quota and usage-limit misrepresentation (I=5, D=3, priority 15)

**Why.** Flat-rate plans profit from under-delivery. The marketed units ("~600 prompts per 5h") are vague; each "prompt" costs an estimated 15–20 calls by Z.ai's own account; and weekly caps, concurrency caps and dynamic throttling can quietly tighten.

**Detect: Quota Exhaustion Run ("QER").**
- **Account.** Use a dedicated account per plan tier. Run a scripted, **realistic** agent trace: replay a recorded Claude Code session of N model calls with typical prompt sizes (30–80k context with caching) at a fixed cadence.
- **Log for every call:** timestamp, HTTP status, error body, `usage` (incl. cached tokens), and response headers (`x-ratelimit-*`, `retry-after`).
- **Stop** at the first hard-limit error. That means 403 on Kimi and "hour allocated quota exceeded" on Alibaba; distinguish these from transient 429s.
- **Compute:**
  - calls, input/output/cached tokens, and "prompts" (agent turns) delivered per window;
  - the time-to-reset curve (rolling window or fixed window?);
  - the weekly cap after repeated windows.
- **Compare** with the advertised numbers via the plan's own conversion ("1 prompt ≈ 15–20 calls"). Report delivered/advertised as the effect size.
- **Repeat** at peak and off-peak times (China business hours vs night). Report the variance, because dynamic quotas are a form of short-changing.
- Also check the rate-limit classification: is a transient TPM throttle reported as `insufficient_quota`? Several tools then disable the key.
- Also compare the provider's **usage dashboard** with locally counted usage. Dashboard over-reporting is token inflation (§2.8).

**Statistic.** Mostly descriptive: delivered units with a range across 3+ windows. Flag if the max across windows is below the advertised value, or if the median is under 70% of it (a pre-registered tolerance).

**Ref?** Absolute against the advertisement.

**Cost.** Expensive in wall-clock time and quota (it consumes the whole window), though cheap in money for flat plans. Do it monthly or quarterly per tier.

**Cites.** [Z.ai devpack overview](https://docs.z.ai/devpack/overview), [Z.ai FAQ](https://docs.z.ai/devpack/faq), [Kimi error reference](https://www.kimi.com/code/docs/en/kimi-code/error-reference.html), [Alibaba error codes](https://www.alibabacloud.com/help/en/model-studio/error-code), [Alibaba Coding Plan FAQ](https://www.alibabacloud.com/help/en/model-studio/coding-plan-faq), [pi #10656](https://github.com/earendil-works/pi/issues/10656), [pawwork #740](https://github.com/Astro-Han/pawwork/issues/740), [Anthropic April 2026 cache-miss quota drain](https://infoq.com/news/2026/05/anthropic-claude-code-postmortem).

### 2.8 Token-accounting inflation (I=3 on flat plans, but quota-relevant; D=5; priority 15)

**Why.** If the quota is token-metered (credits), over-reporting `prompt_tokens`, `completion_tokens` or `reasoning_tokens` exhausts it faster. Under-reporting `cached_tokens` does the same.

**Detect.**
- Compare `usage.prompt_tokens` with the local HF tokenizer plus chat-template count. The PTO regression from §2.6 gives slope b; b > 1 means proportional inflation.
- Compare `completion_tokens` with the local token count of the returned `content` plus `reasoning_content`; with `max_tokens=k`, confirm `completion_tokens ≤ k`.
- For hidden reasoning, check `reasoning_tokens` against the visible-reasoning length, or a PALACE-style predicted range.
- **Streaming vs non-streaming** usage for the same request should match. KVV checks streamed usage.

**Statistic.** Per-call residual; mean residual with a CI. Tolerance is a few tokens of template overhead. Inflation is usually deterministic, so 20–40 calls suffice.

**Ref?** Absolute (local tokenizer), plus the official endpoint as a template sanity check.

**Cost.** Free-riding on other tests: log usage on every call of every test and compute this offline.

**Cites.** [Invisible Tokens, Visible Bills](https://arxiv.org/html/2505.18471v1), [PALACE](https://arxiv.org/html/2508.00912v1), [Token Inflation](https://www.emergentmind.com/papers/2605.30040), [Unite.AI on non-unique tokenization](https://www.unite.ai/?p=218426), [KVV](https://github.com/MoonshotAI/Kimi-Vendor-Verifier).

### 2.9 Prompt-cache misbehaviour (I=4 for agents, D=4, priority 16)

**Why.** Coding agents resend huge prefixes, so caching determines both latency and quota burn.

Failure modes:
- (a) cache hits are reported (`cached_tokens>0`, e.g. for discounted accounting) but no compute is saved. This is harmless to the customer unless quota is charged at full rate.
- (b) the cache is real but **not credited** in usage or quota, which is overcharging.
- (c) cache misses on every turn because the provider mangles the prefix (the Anthropic April 2026 bug drained limits this way).
- (d) **cross-user cache sharing**, a privacy issue (Gu et al.).

**Detect.**
- Build a 30–60k-token prefix P with a fresh random nonce at the start.
- Send P+q₁, then P+q₂ within the TTL, then P′+q₁ with the nonce changed, as the miss control.
- Record TTFT (streamed) and `usage.prompt_tokens_details.cached_tokens` (OpenAI) or `cache_read_input_tokens` (Anthropic).
- Hit-vs-miss TTFT test: Mann–Whitney U on about 15 hit / 15 miss pairs, interleaved in random order.
- Matrix of outcomes:
  - reported hit **and** TTFT drop → honest;
  - no reported hit but TTFT drop → cache not credited (b);
  - reported hit without TTFT drop → (a);
  - neither, on repeated identical prefixes → no caching (c).
- Cross-user check (Gu et al.): account A primes the prefix, account B times it. Do this only with two of our own accounts.
- Also send a **Claude-Code-shaped multi-turn trace** (append-only) and check that `cached_tokens` grows each turn.

**Confounds.** Load-dependent TTFT noise: interleave hit/miss requests and use a rank test. Providers may cache at block granularity.

**Ref?** Absolute.

**Cost.** About 40 calls, with large prompts.

**Cites.** [Gu et al. prompt-cache audit](https://arxiv.org/abs/2502.07776), [Anthropic April 2026 postmortem](https://www.tessl.io/blog/anthropic-postmortem-shows-how-small-changes-compounded-into-claude-code-failure/).

### 2.10 Peak-hour throttling, time-of-day quality changes, queueing, stream stalls (I=4, D=4, priority 16)

**Why.** Plans are oversold. At peak, providers may:
- queue requests (high TTFT);
- lower TPS;
- route to a cheaper or quantized pool (dilution);
- cap output or reasoning dynamically;
- return 429s.

Z.ai's February 2026 compute shortage is an example. Anthropic explicitly says it never degrades quality by load; plans make no such promise.

**Detect: scheduled micro-probes ("TOD").** Every 30–60 min, 24×7 for 2+ weeks, run:
- 3 TPS/TTFT calls (existing benchmark);
- 5 arithmetic-panel items (existing INT4 detector, a small rotating subset);
- 5 IRIS random-generation probes (dilution tells);
- 1 reasoning-length item (§2.3);
- 1 output-cap check.

Log the full SSE timing per chunk and derive:
- TTFT;
- decode TPS;
- p99 and maximum **inter-chunk gap**;
- count of stalls (gaps > 5 s);
- truncated streams (no finish chunk);
- error and 429 rates.

**Statistics.**
- Quality vs hour-of-day: logistic regression of correctness on hour (in Beijing time, given who serves these plans) with a peak/off-peak indicator. Report the odds ratio with a CI.
- Throughput: quantile regression or the Mann–Whitney peak vs off-peak contrast.
- Drift: one-sided **CUSUM** on the standardized daily quality score (see §4).
- Dilution: binomial test on the per-response tell rate per window.

**Ref?** Absolute for latency and errors. Quality comparisons use the plan's own off-peak baseline as the reference, which neatly avoids hardware confounds.

**Cost.** About 15 small calls per probe; 48 probes/day ≈ 700 calls/day/plan. Mostly short, which fits the flat-plan quota.

**Cites.** [Wikipedia: Z.ai compute shortage](https://en.wikipedia.org/wiki/Z.ai), [Anthropic Sept 2025 postmortem](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues), [IRIS](https://arxiv.org/html/2607.20860v1), [Kimi forum 429s](https://forum.moonshot.ai/t/error-code-429-were-receiving-too-many-requests-at-the-moment/191).

### 2.11 Response caching or semantic caching (I=3, D=5, priority 15)

**Why.** Returning stored answers to identical or similar prompts saves compute entirely. A semantic cache is dangerous for code: "fix bug in foo()" and "fix bug in bar()" may get the same answer.

**Detect.**
- **Exact-repeat test.** Send the same prompt 10× at T=1 asking for a ~200-token creative or code answer. Under honest sampling, P(byte-identical outputs) is about 0. Flag if more than one pair is identical or if TTFT collapses to near zero.
- **Nonce control.** Prepend a random nonce, which should restore diversity.
- **Semantic-cache test.** 20 pairs of near-duplicate prompts with **different correct answers** (e.g. "Return the SHA-free checksum: sum of digits of 48213" vs "…48231"; or a function that differs in one constant). Measure the rate at which the second answer equals the first answer rather than its own correct answer. Honest rate ≈ 0.

**Ref?** Absolute.

**Cost.** About 60 calls.

**Note.** Only a real cache that ignores sampling is cheating. Prefix KV caching (§2.9) is legitimate.

### 2.12 Sampling-parameter non-compliance (I=3, D=5, priority 15)

**Why.** A plan may override `temperature`/`top_p` to its own defaults (sometimes legitimately; Moonshot forces T=1.0 and top_p=0.95 in thinking mode), ignore `stop`, `seed`, `n`, `presence_penalty`, `logit_bias` or `response_format`, or ignore `stream_options.include_usage`. This breaks agent tooling (stop sequences) and invalidates our own tests, since several existing tests assume T=0 is honoured.

**Detect: KVV-style parameter pre-flight, run before every other test.**

| Parameter | Probe | Pass criterion |
|---|---|---|
| `temperature=0` | Same prompt ×8 | ≥ about 7/8 identical outputs (calibrate vs official) |
| `temperature` 0 vs 1.5 | First-word entropy on a 10-way choice prompt | Entropy(T=1.5) clearly greater than Entropy(T=0) |
| `top_p=0.01` at T=1 | ×8 | Near-deterministic |
| `stop=["7"]` | "Count 1 to 20" | Output contains no "7" and ends before it; `finish_reason=stop` |
| `seed` | Same seed ×3 vs different seed | Reproducible, or document as unsupported |
| `n=3` | | 3 choices, or a documented error |
| `logit_bias` | Ban token "Paris" on a capital-of-France prompt | |
| `response_format` json_schema | | Valid against the schema |
| `max_tokens` | See §2.2 | |
| Unsupported param | e.g. `foo=1` | Error or silently ignored (document which) |

**Statistic.** Mostly deterministic pass/fail. For entropy, use a permutation test.

**Ref?** Absolute, cross-checked against official behaviour, because the official API may itself override some parameters. If so, that is not plan cheating.

**Cost.** About 40 calls.

**Cites.** [KVV pre-verification](https://github.com/MoonshotAI/Kimi-Vendor-Verifier), [Kimi blog](https://www.kimi.ai/blog/kimi-vendor-verifier).

### 2.13 Output post-processing, filtering, censorship (I=3, D=4, priority 12)

**Why.**
- Regulatory compliance at the reseller layer, often stricter than the vendor's own.
- Moderation proxies that blank or replace content.
- Sanitizers that strip "dangerous" strings: shell commands such as `rm -rf`, special tokens, HTML/JS.

All of these silently corrupt code.

**Detect.**
- **Exact-echo fidelity.** Ask the model to repeat verbatim 30 tricky code blocks: unicode, zero-width characters, `<|im_end|>`-like strings, `</script>`, ANSI escapes, very long lines, `rm -rf /tmp/x`, base64 blobs and keys-like strings (fake). Exact-match rate vs official. A difference means output mutation.
- **Benign-sensitive refusal panel.** 40 legitimate coding tasks that trip filters: security tooling (port scanner, fuzzers), cryptography, scraping, and code containing politically sensitive strings in comments or test data. Compare refusal or `finish_reason=content_filter` rate with the official endpoint using Fisher's exact test.
- Record `finish_reason` values outside {stop, length, tool_calls} and empty responses (AA lists empty responses as a failure mode).

**Ref?** Requires the reference.

**Cost.** About 140 calls.

### 2.14 Coding-quality regression on small executable tasks (I=5, D=3, priority 15)

**Why.** This is the catch-all and the outcome customers actually care about. It catches combinations of all the above, and it is what KVV approximates with SWE-Bench at much higher cost.

**Detect: "MiniExec".**
- **Panel.** 150–300 small, **fresh or contamination-resistant** functions, each with hidden unit tests. Options: a LiveCodeBench-style recent subset, auto-generated variants of HumanEval/MBPP with renamed identifiers and changed constants, or procedurally generated tasks (e.g. "implement this spec of a tiny interpreter"). Include some multi-file "edit this repo" tasks via tool calls (ties into §2.1).
- **Execution.** Run in a local sandbox (subprocess plus timeout, or Docker).
- **Metric.** pass@1 per task, with k=3 samples at the vendor-recommended temperature, giving a per-task pass rate.
- **Statistic.** Paired over tasks: compare per-task pass rates (plan vs official) with a paired permutation test or Wilcoxon. For a single-sample binary outcome, use McNemar. Report the difference in pass@1 with a task-clustered bootstrap CI.
- **Power (α=0.05, 80% power):**
  - Unpaired two-proportion: 80%→70% needs about 290 tasks per arm; 80%→75% needs about 1,090.
  - **Paired McNemar** is far cheaper when discordance is low. With 15% discordant pairs and a 10 pp gap, about 115 tasks; with 10% discordant and a 5 pp gap, about 310.
  - Conclusion: **MiniExec can reliably detect a 10 pp drop with about 150 paired tasks × 3 samples** (about 450 calls per endpoint). It cannot detect a 2–3 pp drop at feasible cost; use the targeted tests above for subtle degradation.
- **Confounds.** Temperature, reasoning effort, and the max-output cap (truncated code fails). Run the configuration tests (§2.2, §2.3, §2.12) first so that failures can be attributed.

**Ref?** Requires the reference. Also report absolute pass rates.

**Cost.** About 450 calls per endpoint, medium output.

### 2.15 Speculative decoding or draft-model leakage (I=2, D=2, priority 4)

**Why.** Standard speculative decoding is **lossless**: output distribution equals the target model's, so it is not cheating. Lossy variants (relaxed or typical acceptance, approximate verification, or serving draft tokens unverified under load) shift the distribution toward the small draft model.

**Detect.**
- Distributional tests (first-word entropy, IRIS tells, MET) catch lossy acceptance as a shift toward the draft model.
- A TPS fingerprint shows whether spec decoding is used at all: TPS much higher on predictable text ("repeat this paragraph") than on high-entropy text (random digits). This is informational, not a violation.
- Flag only if a distribution shift co-occurs with the TPS fingerprint.

**Ref?** Requires the reference. Low priority.

### 2.16 Translation-layer and protocol fidelity, Anthropic-compatible endpoints (I=4, D=5, priority 20; usually folded into §2.1)

**Why.** Many plans offer an Anthropic Messages-compatible endpoint for Claude Code, implemented as a translation proxy. Bugs or shortcuts in that proxy include:
- dropping `thinking` blocks;
- mishandling `cache_control`;
- truncating `tool_result` content;
- ignoring `stop_sequences`;
- mapping `stop_reason` wrongly;
- flattening images;
- breaking streaming event ordering (`content_block_delta`, `input_json_delta`).

**Detect.** Run a protocol conformance suite: a schema check of every SSE event type and order, round-trip a multi-block tool_use/tool_result conversation, and check `usage` fields against the equivalent OpenAI-path request. Pass/fail.

**Ref?** Absolute, against the Anthropic API spec.

**Cost.** About 30 calls.

---

## 3. Priority table

| # | Vector | Impact | Detectability | Priority | Ref needed? | Calls/plan (approx.) | Repo status |
|---|---|---|---|---|---|---|---|
| 2.1 | Tool-call fidelity | 5 | 5 | 25 | Hybrid | 400 (+800 ref, reusable) | **Missing** |
| 2.2 | Output cap / max_tokens / context truncation | 5 | 5 | 25 | Absolute | 30 (+heavy input tokens) | Partial (needles test quality, not limits) |
| 2.3 | Reasoning budget | 5 | 4 | 20 | Ref | 150 per effort level | **Missing** |
| 2.4 | Substitution / aliasing / dilution | 5 | 4 | 20 | Ref-enrolled | 100–700 (KBF) + 10 (tokenizer) + 100 (tells) | Partial (rollout prefix, entropy) |
| 2.6 | Hidden system prompt | 4 | 5 | 20 | Absolute | 50–80 | **Missing** |
| 2.16 | Anthropic-compat protocol | 4 | 5 | 20 | Absolute | 30 | **Missing** |
| 2.9 | Prompt cache | 4 | 4 | 16 | Absolute | 40 | Missing |
| 2.10 | Peak-hour / time-of-day | 4 | 4 | 16 | Self-baseline | about 700/day | Partial (TPS/TTFT only) |
| 2.7 | Quota misrepresentation | 5 | 3 | 15 | Absolute | 1 window | Missing |
| 2.8 | Token-accounting inflation | 3 | 5 | 15 | Absolute | 0 extra (log usage) | Missing |
| 2.11 | Response or semantic caching | 3 | 5 | 15 | Absolute | 60 | Missing |
| 2.12 | Sampling-param compliance | 3 | 5 | 15 | Absolute | 40 | Missing (and a prerequisite for existing T=0 tests) |
| 2.14 | Executable coding regression | 5 | 3 | 15 | Ref | 450 | Missing |
| 2.5 | Quantization (improvements) | 4 | 3 | 12 | Ref | 200–500 | Covered (arithmetic, needles) |
| 2.13 | Post-processing / censorship | 3 | 4 | 12 | Ref | 140 | Missing |
| 2.15 | Lossy speculative decoding | 2 | 2 | 4 | Ref | 0 (from existing) | Implicitly via entropy |

---

## 4. Statistical practice

1. **Calibrate every threshold on reference-vs-reference.** Run the official endpoint at least twice, on different days, and set thresholds from that natural variance, as KVV did (F1 bar at the minimum observed official score) and as AA does (reference 95% CI). Reasons:
   - Production nondeterminism (batching, GPU type) produces non-zero "differences" even between identical deployments (Cai et al.).
   - MMD distances between two instances of the same model can be large.
   - Store the ref-vs-ref effect alongside each test as `null_effect`.
2. **Pre-register panels and hypotheses.**
   - Freeze panel versions (`*_PANEL_ID`, `prompt_hash`, as the framework already does).
   - Fix the primary metric and direction (one-sided "plan is worse" for quality; two-sided for distribution identity).
   - Fix N in advance, or use a sequential design (item 5).
   - Never tune thresholds after seeing a plan's results.
3. **Multiple-testing correction.**
   - **Within one plan's verdict** (family-wise: "is this plan cheating?"): use **Holm–Bonferroni** over the battery of primary tests (about 10–15 tests). Holm is uniformly more powerful than Bonferroni and valid under any dependence.
   - **Across the leaderboard** (plans × models × tests, hundreds of hypotheses): use **Benjamini–Hochberg** FDR at q=0.05 to choose which cells to flag publicly. Use Benjamini–Yekutieli if dependence is a concern; tests on the same endpoint are positively correlated, which BH tolerates (PRDS).
   - Treat secondary or diagnostic metrics (e.g. per-position needle recall) as descriptive, outside the correction family.
   - Prefer few, strong primary endpoints per vector over many weak ones.
4. **Effect sizes with CIs. Never report a bare p-value.**
   - Proportions: risk difference with Wilson or Newcombe CI, plus Cohen's h.
   - Lengths and latencies: median ratio with bootstrap CI, plus Cliff's delta.
   - Distributions: MMD or KS statistic relative to the ref-vs-ref null.
   - Quota: delivered/advertised ratio.
   - Cluster bootstrap **by prompt**: prompts are the unit of generalization, and repeated samples of one prompt are not independent.
5. **Sequential and anytime-valid testing for monitoring** (§2.10, and the gap list's "CUSUM drift").
   - Scheduled probes are peeked at continuously, so fixed-N p-values become invalid.
   - **CUSUM** on standardized per-window scores, S_t = max(0, S_{t−1} + (x_t − μ₀ − k)), alarming at S_t > h. Choose k (half the minimum shift of interest) and h for an in-control average run length of about 1 false alarm per 90 days per plan, estimated by simulation on reference data.
   - For one-shot audits with a stopping option, use an **SPRT/mSPRT** or **e-value/confidence-sequence** test. Example: a betting e-process for a Bernoulli difference stops early when a plan is clearly broken (saving quota) and stays valid under optional stopping.
   - Combine evidence across tests with e-value averaging, which is valid under arbitrary dependence.
6. **Equivalence testing before claiming "at parity".** Failing to reject is not evidence of honesty. Use **TOST** with a pre-declared margin (e.g. ±3 pp on schema accuracy, ±10% on median reasoning length). Label plans "Equivalent", "Not equivalent / inconclusive" or "Worse". AA's "within reference CI" rule is a simplified version of this.
7. **Power planning.** Size N per test using the reference's variance, with formulas or simulation:

   | Comparison (α=0.05, 80% power) | N needed |
   |---|---|
   | Proportions 0.99 vs 0.95 | about 280 per arm |
   | Proportions 0.99 vs 0.97 | about 765 per arm |
   | Paired McNemar, 15% discordant, 10 pp gap | about 115 |
   | Paired McNemar, 10% discordant, 5 pp gap | about 310 |
   | Dilution ε (IRIS) | m ≈ ln(1/δ)/(ε·q) |
   | KBF | N = 109–681 probes |

   Where absolute effects are near 0/100%, as with tool-schema validity on the official endpoint, an exact one-sided binomial against the reference rate's upper confidence bound is efficient.
8. **Mixture-awareness.** Report the estimated contaminated fraction ε̂ (IRIS/KBF) rather than only a binary verdict. Spread samples across time-of-day and days so that peak-only routing is captured, and stratify the analysis by window.
9. **Panel rotation and anti-evasion.**
   - Providers can fingerprint audit traffic (Cai et al., "benchmark evasion"). Rotate panel subsets from a large private pool; generate probes procedurally (arithmetic, KBF facts, IRIS random-gen, MiniExec variants); and interleave probes with realistic agent traffic.
   - The repo already uses `StealthChatClient`, jitter and shuffled schedules. Keep a held-out "canary panel" that is never published.
   - When a panel is rotated, bump `*_PANEL_ID` so that comparability checks stay correct.
10. **Attribution hygiene.** Run the configuration tests (parameter compliance, output cap, PTO system-prompt check) **first** and record them in the artifact metadata. A quality failure then becomes interpretable, e.g. "fails MiniExec because output is capped at 8k", rather than a vague "worse model". This also blocks the AgentProv false-positive mode (system-prompt injection mistaken for substitution).

---

## 5. Ranked recommendation: top 8 new tests

1. **`test_toolcall_fidelity`** (K2VV-style; §2.1, §2.16).
   - Coding-agent tool panel, streaming and non-streaming, OpenAI and Anthropic-compatible paths.
   - Metrics: absolute schema-valid / JSON-parse / undeclared-tool / `tool_choice` compliance / leaked-markup rates, plus reference-relative trigger F1 and propensity ratio. Threshold calibrated on official×2.
   - About 400 calls per plan. **Highest impact, proven in the wild** (schema accuracy 72–100% across K2 vendors).
2. **`test_limits`** (output cap, `max_tokens` respect, context-capacity sweep with head/middle/tail canaries, prompt-tokens truncation check; §2.2).
   - Mostly absolute against advertised specs. About 30 calls (plus a big input budget). AA names this a primary failure mode.
3. **`test_reasoning_budget`** (§2.3).
   - Paired per-prompt reasoning-length ratio (Wilcoxon), effort-level monotonicity, truncated-thinking detection, reported-vs-visible reasoning-token gap.
   - About 150 calls per effort level. Directly addresses the top GLM-5 complaint and the AA findings.
4. **`test_prompt_overhead`** (prompt-token offset regression against local tokenizer and official; cross-length tokenizer differential; system-prompt canary at end of a 20k system prompt; §2.6, §2.4, §2.8).
   - About 80 calls. Nearly free. Detects hidden injection, system-prompt truncation, tokenizer (model-family) mismatch and token inflation. **Run before all distributional tests** to avoid AgentProv-style false positives.
5. **`test_params_preflight`** (KVV-style parameter compliance: T=0 determinism, temperature effect, top_p, stop, seed, n, logit_bias, response_format, unsupported params; §2.12).
   - About 40 calls. A prerequisite that validates the assumptions of the existing T=0 rollout and entropy tests.
6. **`test_kbf_fingerprint`** plus **dilution tells** (§2.4).
   - KBF knowledge-boundary binomial test (one-time official enrolment, about 100–700 probes, under $1). IRIS-style random-generation tells with a binomial test and ε̂ estimate, sampled across the day.
   - Closes the "partial routing" gap that whole-run tests miss.
7. **`test_miniexec`** (executable coding regression; §2.14).
   - 150 fresh or procedurally varied tasks × 3 samples. Paired McNemar or permutation test with a task-clustered CI. Detects about 10 pp drops.
   - The customer-facing outcome metric, and the cheap substitute for KVV's SWE-Bench.
8. **`monitor_tod`** (scheduled micro-probes with CUSUM; §2.10, plus cache and response-cache checks from §2.9 and §2.11 run daily).
   - TTFT, TPS, stall and 429 rates plus small quality and dilution subsets every 30–60 min. Peak-vs-off-peak contrasts and a CUSUM alarm.

**Honourable mentions:**
- **`audit_quota`** (§2.7): monthly full-window exhaustion run per tier. High impact, but it consumes quota and wall-clock time.
- **Prompt-cache audit** (§2.9).
- **Exact-echo / refusal panel** (§2.13).
- **Logprob tracking** (LPT/RUT) where plans expose logprobs. Record "logprobs unsupported" as a transparency datum.

All of these fit the repo's fidelity-test contract: a single-endpoint runner, a self-describing `summary.json`, a pure `compare_*`, and `assert_comparable`. The absolute tests (2, 4, 5, the quota audit, and the cache checks) can emit a `RunResult` that `compare.py` evaluates against advertised-spec metadata instead of a reference run. That needs a small framework extension: a "spec" pseudo-reference.

---

## 6. Source list

- MoonshotAI K2-Vendor-Verifier: https://github.com/MoonshotAI/K2-Vendor-Verifier
- MoonshotAI Kimi-Vendor-Verifier: https://github.com/MoonshotAI/Kimi-Vendor-Verifier
- Kimi Vendor Verifier blog: https://www.kimi.ai/blog/kimi-vendor-verifier
- GIGAZINE on KVV: https://gigazine.net/gsc_news/en/20260421-kimi-vendor-verifier/
- evalscope K2VV docs: https://evalscope.readthedocs.io/en/v1.13.0/benchmarks/k2_verifier.html
- vLLM Kimi K2 tool-calling debugging: https://vllm.ai/blog/2025-10-28-kimi-k2-accuracy
- OpenRouter, Provider Variance / Exacto: https://openrouter.ai/blog/announcements/provider-variance-introducing-exacto/
- OpenRouter, Auto Exacto: https://openrouter.ai/blog/announcements/auto-exacto/
- GreaterWrong, "Not pinning your OpenRouter provider…": https://www.greaterwrong.com/posts/KsyoSAyBRXtwzSugg/not-pinning-your-openrouter-provider-might-invalidate-your
- Artificial Analysis, Endpoint Accuracy Index methodology: https://artificialanalysis.ai/methodology/endpoint-accuracy-index
- Artificial Analysis, Endpoint Accuracy Index article: https://artificialanalysis.ai/articles/endpoint-accuracy-index
- Artificial Analysis, gpt-oss-120b providers: https://artificialanalysis.ai/models/gpt-oss-120b/providers
- Simon Willison on provider inconsistency: https://feeds.simonwillison.net/2025/Aug/15/inconsistent-performance/
- ndurner on provider inconsistencies: https://ndurner.substack.com/p/ai-inference-provider-inconsistencies
- Gao et al., Model Equality Testing: https://arxiv.org/abs/2410.20247
- Cai et al., Are You Getting What You Pay For?: https://arxiv.org/html/2504.04715v1
- RUT: https://arxiv.org/abs/2506.06975
- Idiosyncrasies in LLMs: https://arxiv.org/abs/2502.12150
- Log Probability Tracking: https://arxiv.org/abs/2512.03816
- B3IT, Token-Efficient Change Detection: https://arxiv.org/abs/2602.11083
- KBF: https://arxiv.org/html/2605.29524v2
- IRIS: https://arxiv.org/html/2607.20860v1
- AgentProv: https://arxiv.org/abs/2609.00052
- Four-stage identity protocol: https://arxiv.org/html/2608.31142v1
- Shadow APIs: https://arxiv.org/abs/2603.01919
- Invisible Tokens, Visible Bills: https://arxiv.org/html/2505.18471v1
- PALACE: https://arxiv.org/html/2508.00912v1
- Token Inflation: https://www.emergentmind.com/papers/2605.30040
- Unite.AI on tokenization incentives: https://www.unite.ai/?p=218426
- Prompt-cache audit (Gu et al.): https://arxiv.org/abs/2502.07776
- TOPLOC: https://arxiv.org/html/2501.16007v2
- Anthropic Sept 2025 postmortem: https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
- Anthropic April 2026 Claude Code postmortem coverage (InfoQ): https://infoq.com/news/2026/05/anthropic-claude-code-postmortem
- Anthropic April 2026 Claude Code postmortem coverage (The Register): https://www.theregister.com/2026/04/23/anthropic_says_it_has_fixed/
- Anthropic April 2026 Claude Code postmortem coverage (Tessl): https://www.tessl.io/blog/anthropic-postmortem-shows-how-small-changes-compounded-into-claude-code-failure/
- Efficienist on GLM-5 coding-plan complaints: https://efficienist.com/users-report-declining-quality-on-z-ais-glm-5-coding-plans/
- Wikipedia, Z.ai: https://en.wikipedia.org/wiki/Z.ai
- Z.ai devpack overview: https://docs.z.ai/devpack/overview
- Z.ai devpack FAQ: https://docs.z.ai/devpack/faq
- Kimi Code error reference: https://www.kimi.com/code/docs/en/kimi-code/error-reference.html
- Kimi forum 429 thread: https://forum.moonshot.ai/t/error-code-429-were-receiving-too-many-requests-at-the-moment/191
- pawwork issue #740: https://github.com/Astro-Han/pawwork/issues/740
- Alibaba Model Studio error codes: https://www.alibabacloud.com/help/en/model-studio/error-code
- Alibaba Coding Plan FAQ: https://www.alibabacloud.com/help/en/model-studio/coding-plan-faq
- pi issue #10656: https://github.com/earendil-works/pi/issues/10656
- OpenRouter message transforms (middle-out): https://openrouter.ai/docs/features/message-transforms
- CSDN relay-detection guide: https://aicoding.csdn.net/6a44780010ee7a33f285443e.html
- CSDN detection-tool comparison: https://aicoding.csdn.net/6a6873d6662f9a54cb952e4e.html
- apito.ai on verifying Claude API authenticity: https://apito.ai/zh/blog/getting-started/how-to-verify-claude-api-authenticity-fingerprint-detection/
