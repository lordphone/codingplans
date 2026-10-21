# AI Coding Plans Landscape (research snapshot, 2026-10-20)

Scope: flat-rate subscriptions that hand out an API key / endpoint usable from coding agents (Claude Code, Cline, Roo, OpenCode, Kilo, ...). For each plan: tiers, price, limits, models, plan endpoint, the official pay-as-you-go (PAYG) reference endpoint, parameter support relevant to fidelity testing (logprobs, seed, thinking toggle), ToS restrictions relevant to programmatic benchmarking, open-weight status, and public under-delivery reports.

**Confidence legend.** [O] = read on an official vendor page during this research. [3P] = third-party tracker or blog only (unverified). [?] = not found / unknown. Prices move monthly in this market (several plans were repriced, renamed, or retired Aug-Oct 2026), so re-check before publishing anything on the site.

**Key landscape shifts in 2026 (context):**
- Many CN vendors moved from "N prompts / 5h" to **credit/token-metered "Token Plans"** (Alibaba, MiniMax, Xiaomi, Tencent, Baidu, StepFun, Volcengine Agent Plan). Requests-per-5h plans survive at Alibaba (Coding Plan Pro), Volcengine (Coding Plan), and a few clouds.
- **Silent routing / aliasing is now documented policy at several vendors** (e.g. Z.ai routes `glm-5.2`/`glm-5.1` requests to GLM-5.3 and `glm-4.7` to GLM-5.3-Flash; MiniMax routes M2.5/M2.7 to M3.1-Flash; Kimi `kimi-for-coding` is a moving alias). This matters for our model-identity tests: a model ID string on a plan does not pin the weights.
- **Thinking cannot be disabled** on several 2026 flagships (MiniMax M3/M3.1-Flash, Kimi K3 and K2.7-Code), and sampling params are forced (Kimi forces T=1.0/top_p=0.95 in thinking mode; MiniMax ignores temperature). Temperature-0 / greedy determinism-based fidelity tests will not work on these.
- **Several plan ToS explicitly forbid non-interactive / scripted use** (Alibaba, Chutes subscriptions, Z.ai "supported tools only", Kimi forbids User-Agent tampering, Anthropic subscriptions). See ToS column; this is the main operational risk for our benchmark harness.

Global aggregator sources used for cross-checking:
- jia.je coding-plan knowledge base (very detailed CN-focused changelog, last entry 2026-10-19): https://jia.je/kb/en/software/coding_plan.html [3P]
- codingplan.org (updated 2026-09-24): https://codingplan.org/en [3P]
- codepick.dev comparison (updated 2026-08-26): https://codepick.dev/en/compare/coding-plan-comparison-2026/ [3P]

---

## 1. Z.ai / Zhipu — GLM Coding Plan

| Field | Value |
|---|---|
| Tiers / price | Lite $18/mo ($12.6/mo yearly), Pro $80/mo, Max $168/mo [O for Lite $18; 3P for Pro/Max]. CN: Lite ¥118, Pro ¥538, Max ¥1,078 [3P]. Team Standard ¥598/seat, Advanced ¥1,198/seat [3P]. Old ¥49/149/469 and 80/400/1600-prompt figures are obsolete. |
| Limits | Credit-metered: Lite 2,000 credits/5h + 10,000/week; Pro 12,000/60,000; Max 28,000/140,000 [O]. Credits = (in×coef + cached×coef + out×coef)/10,000; GLM-5.3 coefs 6.9/1.7/24, GLM-5.3-Flash 2.3/0.56/8 [O]. Off-peak = 50% rate; peak Mon–Fri 14:00–18:00 UTC+8 [O]. Suggested concurrency: Lite 1, Pro 1–2, Max 2+ [O]. |
| Models | GLM-5.3, GLM-5.3-Flash. Requests for GLM-5.2/5.1 are **routed to GLM-5.3**; GLM-4.7 (and GLM-5-Turbo) → GLM-5.3-Flash [O]. Context up to 1M [3P]. |
| Plan base URLs | Anthropic: `https://api.z.ai/api/anthropic`; OpenAI Chat: `https://api.z.ai/api/coding/paas/v4`; OpenAI Responses: `https://api.z.ai/api/v1` [O]. CN equivalents on `open.bigmodel.cn` [?]. |
| Official PAYG reference | `https://api.z.ai/api/paas/v4` (chat at `/chat/completions`), models `glm-5.3`, `glm-5.2`, `glm-5.1`, `glm-5`, `glm-4.7`, `glm-4.6`, `glm-5.3-flash(x)` [O]. Env: `ZAI_API_KEY`. Plan keys and PAYG keys are separate categories [O]. |
| Params | `thinking: {type: enabled|disabled}` (+ `clear_thinking`), `do_sample` (false = greedy), temperature 0–1, top_p [O]. **logprobs / top_logprobs / seed: not documented** [O, absent]. `do_sample:false` is a useful deterministic-ish knob. |
| ToS | "strictly limited to use within officially supported tools and products" (Claude Code, Roo, Kilo, Cline, OpenCode, OpenClaw, Crush, Goose, Cursor...). Detected SDK/third-party use may restrict benefits; >3 violations may lead to ban; no account sharing [O: https://docs.z.ai/devpack/usage-policy, https://docs.z.ai/devpack/quick-start]. **High risk** for scripted benchmarking. |
| Open weights | GLM-5.3: yes, HF `zai-org/GLM-5.3`, custom "glm-5.3" license, ~753B/40B active MoE, BF16+FP8 checkpoints, vLLM/SGLang supported; weights ~Aug 28–29 2026 [3P: https://gigazine.net/gsc_news/en/20260829-glm-5-3-open/, https://thenewstack.io/zai-glm-weights-license/]. GLM-5.3-Flash: MIT [3P]. **Good self-host anchor.** |
| Under-delivery reports | Mar 2026: r/ZaiGLM users (mainly Max) report GLM-5 quality decline after "performance improvements", shortened thinking, suspected quantization, degradation >80–100k tokens [3P: https://efficienist.com/users-report-declining-quality-on-z-ais-glm-5-coding-plans/; https://huggingface.co/zai-org/GLM-5.1/discussions/5]. No official response found. |

Sources: https://docs.z.ai/devpack/overview, https://docs.z.ai/devpack/quick-start, https://docs.z.ai/devpack/usage-policy, https://docs.z.ai/api-reference/llm/chat-completion

## 2. Moonshot — Kimi Code (Kimi For Coding, via Kimi membership)

| Field | Value |
|---|---|
| Tiers / price | New plans (from ~Sep 18 2026): Go ¥49 (no coding quota), Plus ¥99 (¥79 annual), Pro ¥199, Max ¥699 [3P codingplan.org]. Legacy USD tiers: Moderato $19, Allegretto $39, Allegro $99, Vivace $199 [3P codepick]. **New subscriptions paused July 2026 due to K3 compute shortage**; renewal prioritized for existing subs until 2026-08-20 [3P: https://www.caixinglobal.com/2026-07-20/tech-brief-jul-20-moonshot-ai-pauses-new-kimi-subscriptions-102466148.html, jia.je]. Check current availability. |
| Limits | 5-hour rolling window + monthly total quota; weekly window removed for new members [O: membership page]. No numeric quotas published [O]. Extra Usage billable in RMB [O]. All tools/devices/API keys share one quota [O]. Up to 5 API keys/member [O]. |
| Models (plan IDs) | `k3` (Plus+; 1M ctx on Pro+), `k3-256k` (~half quota), `kimi-for-coding` (= K2.8 Preview, moving alias), `kimi-for-coding-highspeed` (K2.7 Code HighSpeed, Pro+) [O]. Up to ~260 tok/s claimed [3P]. |
| Plan base URLs | OpenAI (Chat + Responses): CN `https://api.kimi.com/coding/v1`, overseas `https://api.kimi.ai/coding/v1`; Anthropic: CN `https://api.kimi.com/coding/`, overseas `https://api.kimi.ai/coding/` [O]. |
| Official PAYG reference | `https://api.moonshot.ai/v1` (CN `https://api.moonshot.cn/v1`); IDs `kimi-k3`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed`, `kimi-k2.6` [O: https://platform.kimi.ai/docs/api/chat]. Env suggestion: `MOONSHOT_API_KEY`. |
| Params | **`logprobs` + `top_logprobs` (0–20) supported** [O]. `seed` not documented. `kimi-k3`: `reasoning_effort` low/high/max, thinking cannot be disabled; `kimi-k2.7-code`: thinking `disabled` returns error; `kimi-k2.6`: `thinking:{type:disabled}` allowed [O]. Sampling forced to T=1.0/top_p=0.95 in thinking mode (vendor-verifier blog) [O]. |
| ToS | "Tampering with the client identifier (User-Agent) is treated as a violation" → suspension of benefits [O: https://www.kimi.com/code/docs/en/]. Membership is for coding scenarios; third-party tools allowed and share quota [O]. **Medium-high risk**: must send an honest UA; scripted calls not explicitly banned. |
| Open weights | K3: yes, HF, custom "Kimi K3 License" (not MIT; revenue/MAU conditions), ~2.8T params, ~1.5 TB, released 2026-07-27 [3P: https://llmgateway.io/blog/kimi-k3-open-weights, https://simonwillison.net/tags/kimi/]. K2.x: modified-MIT open weights. Self-hosting K3 is very expensive. |
| Under-delivery / verification | Moonshot publishes **Kimi Vendor Verifier** (OCRBench, MMMU-Pro, AIME2025 long-output for quantization, ToolCall F1/schema, SWE-Bench) and found "widespread" third-party deviations, much from decoding-param misuse [O: https://www.kimi.com/en/blog/kimi-vendor-verifier; https://github.com/MoonshotAI/Kimi-Vendor-Verifier; https://github.com/MoonshotAI/K2-Vendor-Verifier]. For K3 only Modal and Fireworks reportedly submitted full results, all within error margins [3P]. Capacity crunch / signup pause July 2026 [3P]. **Directly reusable methodology for us.** |

## 3. MiniMax — M Plan (formerly Token Plan, formerly Coding Plan)

| Field | Value |
|---|---|
| Tiers / price | M Plan (launched ~2026-09-30): Go ¥49 / $22, Explore ¥119 / $55, Build ¥469 / $132; annual = 10× monthly [3P jia.je]. Explore = 3× Go; Build = 7.5× (intl) / 12× (CN) [O for multipliers]. Legacy Token Plan Plus/Max/Ultra $20/$50/$120 → raised to $22/$55/$132 Aug 2026 [3P: https://usagepricing.com/blueprint/activity/minimax-2026-08-26-price-change]. |
| Limits | Unified meter (text/image/audio) with 5-hour and weekly windows; no numeric caps published [O/3P]. |
| Models | MiniMax-M3.1-Flash on all tiers (1M ctx); H3 video on Explore/Build [O]. M2.5/M2.7 closed to new users 2026-10-19, retire 2026-11-18, plan requests **route to M3.1-Flash** [3P jia.je]. M3.1-Flash-Preview retired → served by M3.1-Flash [O]. |
| Plan base URLs | Same hosts as PAYG with an M Plan key from `platform.minimax.io/console/plan`: Anthropic `https://api.minimax.io/anthropic` (recommended), OpenAI `https://api.minimax.io/v1`; CN `https://api.minimaxi.com/...` [O for hosts; plan-key mapping 3P]. |
| Official PAYG reference | Same URLs, PAYG key; IDs `MiniMax-M3.1-Flash`, `MiniMax-M3` [O]. Env: `MINIMAX_API_KEY`. |
| Params | **Thinking always on**; `thinking:{type:disabled}` / `effort:"none"` → 400 [O]. `reasoning_effort` low…max; `reasoning_split`; temperature ignored (fixed 1); n=1 only [O]. logprobs/seed not documented [O, absent]. **Weak for logprob-based fidelity.** |
| ToS | No explicit automation ban found; plan and PAYG keys/pools are separate [3P]. **Medium/unknown risk.** |
| Open weights | MiniMax-M3: yes, HF `MiniMaxAI/MiniMax-M3`, 428B/23B active, 1M ctx, official MXFP8 quant; license custom/unclear [3P: https://howaiworks.ai/blog/minimax-m3-open-source-hugging-face.md]. M3.1-Flash: [?] no evidence of weights. |
| Under-delivery reports | None specific found. Repeated product renames/price hikes and forced routing to M3.1-Flash are the notable changes. |

Sources: https://platform.minimax.io/docs/guides/text-generation.md, https://platform.minimax.io/docs/guides/pricing-token-plan.md, https://platform.minimax.io/docs/api-reference/text-openai-api

## 4. Alibaba Cloud Model Studio — Coding Plan (intl) and Bailian Token Plan

| Field | Value |
|---|---|
| Tiers / price | **Coding Plan Pro $50/mo intl** (CN ¥200, ¥39.9 first month promo) [O]. Lite closed to new subs 2026-03-20, renewals ended 2026-04-13 [O]. Slots limited, restocked daily 00:00 UTC+8 [O]. Separate **Token Plan** (CN, credit-based): Lite ¥39 promo/¥60, Essential ¥79/¥120, Standard ¥139/¥180, Pro ¥499/¥600 per month; monthly credits 11,500/25,500/45,000/180,000 [3P jia.je]. |
| Limits | Coding Plan Pro: 6,000 req/5h, 45,000/week (resets Mon 00:00 UTC+8), 90,000/month; may be queued/throttled under load [O]. |
| Models (Coding Plan intl, doc updated 2026-10-11) | `qwen3.7-plus`, `qwen3.6-plus`, `kimi-k2.5`, `glm-5`, `MiniMax-M2.5` (recommended), `qwen3.5-plus` (additional); "models not on this list are not supported" [O]. Note the model list was **trimmed 2026-10-10** [3P]; our `providers.json` still lists `qwen3-max-2026-01-23` and `qwen3-coder-plus` which are no longer on the official list. Token Plan has newer models (qwen3.8-max/flash, glm-5.3, kimi-k3, deepseek-v4.x) [3P]. |
| Plan base URLs | Intl OpenAI: `https://coding-intl.dashscope.aliyuncs.com/v1`; Intl Anthropic: `https://coding-intl.dashscope.aliyuncs.com/apps/anthropic` [O]. CN: `https://coding.dashscope.aliyuncs.com/v1`, `.../apps/anthropic` [3P]. Keys `sk-sp-…` (not interchangeable with `sk-…`) [O]. |
| Official PAYG reference | Model Studio OpenAI-compatible: Singapore `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`, US `https://{WorkspaceId}.us-east-1.maas.aliyuncs.com/compatible-mode/v1` (legacy `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) [O]. Region-specific keys. Env: `DASHSCOPE_API_KEY`. For third-party models (GLM/Kimi/MiniMax) the true reference is the vendor's own API, not DashScope. |
| Params | `seed` supported (uint64) [O]. `enable_thinking` (extra_body) + `thinking_budget` for hybrid Qwen models [O]. logprobs: response field exists but documented as null; request param not documented [O]. |
| ToS | "Do not use the plan's API key for automated scripts, application backends, or other non-interactive scenarios"; violations → suspension / key revocation; single user; non-refundable [O: https://www.alibabacloud.com/help/en/model-studio/coding-plan]. **High risk** — our current benchmark target (`glm5-alibaba`) is squarely in the prohibited category. |
| Open weights | glm-5, kimi-k2.5, MiniMax-M2.5: open. qwen3.x-plus: closed (API-only). Qwen3.8-Max: reported open-weight (2.4T/95B) but HF availability unconfirmed [3P: https://www.baseten.co/library/qwen-38-max/]. |
| Under-delivery reports | No public quantization reports found for the Alibaba plan endpoints (search came up empty). Docs admit queueing/throttling under load. |

## 5. Volcengine Ark (ByteDance) — Coding Plan / Agent Plan

| Field | Value |
|---|---|
| Tiers / price | Coding Plan Lite ¥40/mo (~1,200 req/5h, 9,000/week, 18,000/month), Pro ¥200 (5× Lite) [3P]. ¥9.9/¥49.9 promos are for **Agent Plan** Small/Medium, not Coding Plan [3P]. Agent Plan (AFP points): Small ¥40, Medium ¥200, Large ¥500, Max ¥1,000 [3P jia.je]. Intl via BytePlus ModelArk [3P]. |
| Models | `ark-code-latest` (auto-routing alias), Doubao-Seed-2.1 pro/lite, GLM-5.3/5.3-Flash, Kimi-K3, Kimi-K2.8-Preview, DeepSeek-V4-Pro/Flash, DeepSeek-V4.1-Flash; Kimi-K2.7-Code and MiniMax-M3 being retired; GLM-5.2 removed Aug 31 [3P]. |
| Plan base URLs | OpenAI: `https://ark.cn-beijing.volces.com/api/coding/v3`; Anthropic: `https://ark.cn-beijing.volces.com/api/coding` [3P: https://codepick.dev/en/guides/ark-coding-plan-guide/, https://mastra.ai/models/providers/volcengine-coding-plan.md]. Env convention `ARK_CODING_PLAN_API_KEY` [3P]. |
| Official PAYG reference | Ark standard `https://ark.cn-beijing.volces.com/api/v3` (for Doubao, the vendor API *is* Ark) [3P]. |
| Params / ToS / weights | [?] not verified on official pages. Doubao = closed. `ark-code-latest` auto-routing makes identity testing inherently ambiguous. |

## 6. Xiaomi — MiMo Token Plan

| Field | Value |
|---|---|
| Tiers / price | Lite $6 / ¥39, Standard $16 / ¥99, Pro $50 / ¥329, Max $100 / ¥659 per month; monthly credits 4.1B / 11B / 38B / 82B (raised from 60M…1.6B in May 2026) [3P citing official docs: https://mimo.mi.com/docs/en-US/tokenplan/Token%20Plan/subscription]. 0.8× consumption 00:00–08:00 [3P]. No 5h/weekly caps [3P]. |
| Models | `mimo-v2.6-pro`, `mimo-v2.6-flash`, `mimo-v2.6-pro-ultraspeed`; **mimo-v2.5-pro / mimo-v2.5 retire 2026-10-21 10:00 Beijing** (tomorrow) [O]. 1M ctx [3P]. |
| Plan base URLs | OpenAI `https://token-plan-cn.xiaomimimo.com/v1`; Anthropic `https://token-plan-cn.xiaomimimo.com/anthropic` [O]; also `token-plan-sgp` / `token-plan-ams` hosts [3P]. Keys `tp-` (individual), `ttp-` (team) [O]. "Base URL on the Token Plan page prevails" [O]. |
| Official PAYG reference | `https://api.xiaomimimo.com/v1` (OpenAI), `/anthropic/v1/messages` (Anthropic); `sk-` keys [O]. Env suggestion `MIMO_API_KEY`. |
| Params | Thinking toggle referenced (docs recommend disabling for tool calls) but param name not captured; logprobs [?]. |
| ToS | Supported in listed AI programming tools; content moderation on input+output [O]. No explicit automation ban found. **Low-medium/unknown.** |
| Open weights | MiMo-V2.6 Pro (~1.02T/42B) and Flash (~310B) open under MIT [3P: https://digg.com/ai/2zuvka0r]. Good anchor candidate. |

## 7. StepFun — Step Plan

| Field | Value |
|---|---|
| Tiers / price | Mini ¥49 (400M credits), Plus ¥99 (1.6B), Pro ¥199 (8B), Max ¥699 (40B) monthly; quarterly/yearly discounts [3P jia.je]. Launched 2026-03-23 [3P ifanr]. International "StepFun Coding Plan" exists (no details) [3P]. |
| Models | `step-5-preview` (2× credits at peak), `step-3.7-flash`, `step-3.5-flash(-2603)`, `step-router-v1` [3P]. |
| Plan base URLs | CN Anthropic `https://api.stepfun.com/step_plan`, OpenAI `https://api.stepfun.com/step_plan/v1`; intl OpenAI `https://api.stepfun.ai/step_plan/v1` [3P]. |
| Official PAYG | `https://api.stepfun.ai/v1` (intl) / `https://api.stepfun.com/v1` (CN) [3P]. |
| Open weights | Step-3.5-Flash open [3P]; step-5-preview [?]. Params/ToS [?]. |

## 8. Baidu Qianfan

| Field | Value |
|---|---|
| Plans | Token Plan: Mini ¥9.9 (10M tokens), Lite ¥40 (42M), Pro ¥200 (230M), Max ¥600 (700M); Coding Plan Lite ¥40 / Pro ¥200 (1,200 / 6,000 req per 5h) — **Coding Plan frozen ("model updates stopped", migrate to Token Plan)** [3P jia.je]. |
| Models | DeepSeek-V4-Pro/Flash, GLM-5.2/5.1, Kimi-K2.6, ERNIE 5.1 [3P]. |
| Endpoints / ToS / params | [?] (Qianfan v2 OpenAI-compatible host `https://qianfan.baidubce.com/v2` is the usual PAYG host — unverified for plans). |

## 9. Tencent Cloud — Token Plans (Coding Plan discontinued)

| Field | Value |
|---|---|
| Plans | Coding Plan (launched Mar 2026, Lite ¥40/Pro ¥200) reportedly discontinued in favor of Token Plans [3P]. Personal Hy Token Plan Lite ¥28 … Max ¥468; Personal Universal Token Plan Lite ¥39, Standard ¥99, Pro ¥299, Max ¥599 [3P jia.je]. Credit-based since 2026-08-31. |
| Models | Hy3, Hy4-preview, GLM-5.3, Kimi K2.7 Code / K3, MiniMax-M3, DeepSeek V4/V4.1 (incl. "Official direct-supply" vs non-official variants — interesting for fidelity), MiMo-V2.6 [3P]. GLM-5/5.1/5-Turbo removed 2026-10-15 [3P]. |
| Endpoints / ToS | [?] Base URL not verified (lkeap host unconfirmed). |

## 10. DeepSeek — no flat-rate coding plan (reference API only)

| Field | Value |
|---|---|
| Plan | None found. Accessible through plans at Alibaba, Volcengine, Tencent, Baidu, OpenCode Go, Synthetic, Chutes, Ollama. |
| Official PAYG | OpenAI `https://api.deepseek.com`; Anthropic `https://api.deepseek.com/anthropic` [O]. IDs: `deepseek-flash` (now DeepSeek-V4.1-Flash-1017; legacy `deepseek-v4-flash` still accepted), `deepseek-v4-pro` [O]. Peak/off-peak pricing (peak 2×, Mon–Fri 09–12, 14–18 Beijing) [3P]. Env `DEEPSEEK_API_KEY`. |
| Params | **`logprobs` + `top_logprobs` (0–20) supported** [O]. `thinking:{type:disabled}` or `reasoning_effort:"none"` disables thinking; temperature ignored in thinking mode [O]. seed not documented. |
| Open weights | V4 Flash (284B/13B) and V4 Pro: MIT open weights [3P]; V4.1-Flash weights unconfirmed. |
| Notes | DeepSeek briefly planned to route V4-Pro to V4.1-Flash after 2026-09-14 and reversed on 2026-09-12 [3P jia.je]. |

## 11. OpenCode Go (aggregator plan, popular in 2026)

| Field | Value |
|---|---|
| Tiers | Go $10/mo; Go Plus $40/mo (launched 2026-09-28, 2–8× limits) [3P]. Per-model monthly dollar allowances; 5h = 20% and weekly = 50% of monthly [3P]. |
| Models | ~29–32 incl. GLM-5.3/5.3-Flash, Kimi K3/K2.7 Code, MiniMax M3, MiMo, Qwen3.8/3.7, DeepSeek V4.1 Flash/V4 Pro, plus closed models (GPT 6 Luna, Claude Haiku 5.5, Gemini) [3P]. |
| Endpoints | OpenAI `https://opencode.ai/zen/go/v1/chat/completions` (also documented as `https://opencode.ai/inference/go/openai/v1`), Anthropic `.../messages`; **requests must send `x-opencode-session` header** [3P jia.je]. |
| ToS | One subscriber per workspace [3P]. |

## 12. Chutes (Bittensor-based decentralized inference)

| Field | Value |
|---|---|
| Tiers | PAYG default; Plus $10/mo (2,000 req/day, $50 monthly cap, $4.17/4h burst, 6% off overflow), Pro $20/mo (5,000/day, $100 cap, $8.33/4h, 10% off) [O: https://chutes.ai/pricing]. (A $3 "Base" tier appears in older 3P listings.) |
| Models | Kimi-K3, Kimi K2.6, GLM-5.2, GLM-5.1, DeepSeek-V4-Flash-0731, DeepSeek-V3.2, Qwen3.x, gemma-4… all on TEE compute, IDs carry `-TEE` suffix [O]. |
| Base URL | `https://llm.chutes.ai/v1` [O, from example]. |
| ToS | "Subscriptions are meant for casual, direct use. Automated or high-volume workloads must use pay-as-you-go" [O]. **High risk on subscription; use PAYG for benchmarking.** |
| Notes | Open-weight-only catalog; precision not stated. Historic community suspicion of quantization on decentralized providers; no 2026 report found. |

## 13. Synthetic.new

| Field | Value |
|---|---|
| Tiers | Go $9, Standard $30, Big $90 per month; weekly-regenerating credits at discounted rates; Big has beta "Fast mode" (2× speed, 2× quota) and "Infinite mode" (unmetered, slow, DeepSeek V4.1 Flash only) [O: https://synthetic.new/pricing]. Older 3P: Standard 135 msgs/5h, Pro 1,350/5h (stale). |
| Models | `hf:`-prefixed HF IDs, e.g. `hf:moonshotai/Kimi-K3`, `hf:zai-org/GLM-4.7-Flash`; GLM-5.3 (beta), GLM-5.3-Flash, DeepSeek-V4.1-Flash, Qwen3.8-27B, gpt-oss-120b, Nemotron-3-Super NVFP4 [O]. `syn:` category aliases [O]. |
| Base URLs | OpenAI `https://api.synthetic.new/openai/v1`; Anthropic `https://api.synthetic.new/anthropic/v1` (clients often use `/anthropic`) [O]. |
| ToS / precision | No-train / no-store privacy statement [O]. Precision not stated (one listed model is explicitly NVFP4) [O]. Publishes Synbad eval suite [O]. Automation policy [?]. |

## 14. Ollama Cloud

| Field | Value |
|---|---|
| Tiers | Free; Pro $20/mo ($60 usage credit, 3 concurrent); Max $100/mo ($300 credit, 10 concurrent); Team $500/mo ($1,000 shared) [O: https://ollama.com/pricing]. Switched to token-metered credits ~2026-08-31 [3P]. |
| Models | ~30 `:cloud` models, e.g. `kimi-k3`, `deepseek-v4.1-flash`, `gpt-oss:120b` [O]. |
| Precision | "Native weights, as released by the model provider", but "may use accelerated formats … such as NVFP4" on Blackwell/Vera Rubin [O] — i.e. quantization is explicitly possible. |
| Base URL | `https://ollama.com/api` (native) / `https://ollama.com/v1` OpenAI-compat [?, from docs.ollama.com; unverified here]. One account per person [O]. |

## 15. Cerebras Code

| Field | Value |
|---|---|
| Tiers | Code Pro $50/mo (24M tokens/day), Code Max $200/mo (120M tokens/day); per-minute caps (~300k/400k TPM) [3P]. Reported **sold out** as of 2026-10-05 [3P: https://www.usagepricing.com/blueprint/activity/cerebras-2026-10-05-qwen-3-8-developer-tier-merge]. |
| Models | ZAI-GLM-4.7 per FAQ (cerebras.ai/code page mentions GLM-4.6) — conflicting [3P]. GLM-4.7 removed from public PAYG card 2026-08-17 [3P]. Speed claim up to ~1,000–2,000 tok/s; InfoWorld (Sep 2025) reported 429s after short bursts [3P: https://www.infoworld.com/article/4055909/]. |
| Base URL | `https://api.cerebras.ai/v1` (OpenAI) [3P]. Model id historically `zai-glm-4.7` [3P]. |
| Notes | Wafer-scale hardware; precision historically disputed for some models. Old model (GLM-4.7) — lower relevance in Oct 2026. |

## 16. Groq, Nebius, iFlow

- **Groq**: no flat-rate coding plan found; free tier + PAYG Developer tier only [3P].
- **Nebius (Token Factory, ex-AI Studio)**: PAYG only, "fast" vs "base" flavors per model; no subscription found [3P].
- **iFlow**: iFlow CLI announced end of service **2026-04-17**, users told to migrate to Qoder; free `https://apis.iflow.cn/v1` status unknown [3P: https://github.com/router-for-me/CLIProxyAPI/issues/2561]. Treat as defunct.

## 17. Other CN clouds reselling open models (from jia.je, [3P])

JD Cloud Coding Plan (Lite ¥40 / Pro ¥200, stale models GLM-5, Kimi-K2.5, MiniMax-M2.5), iFlytek Astron Coding Plan (¥39 / ¥199), China Telecom CTCloud Token Plan (¥29–¥699), Huawei Cloud MaaS Token Plan (¥59–¥799), plus Kuaishou KwaiKAT, SenseTime, Infini, Moore Threads, UniAI. All resell the same open-weight models (GLM, Kimi, DeepSeek, MiniMax) — prime audit targets, since they have no first-party stake in model quality.

## 18. Western reference points

| Provider | Plans / price | Models | Endpoint / ToS notes |
|---|---|---|---|
| Anthropic Claude Pro/Max | Pro $20 ($17 annual), Max 5× $100, Max 20× $200; 5h + weekly windows; Fable 5.1 capped at 50% of weekly on Max, credit-billed on Pro [3P codingplan.org] | Fable 5.1, Opus 5.5, Sonnet 5, Haiku 4.5 | Subscription OAuth tokens restricted to Claude Code / Claude.ai since Jan–Feb 2026; third-party harnesses need API key / extra usage [3P: https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/]. Not a benchmark target (closed weights; no plan-vs-API divergence to audit); PAYG `https://api.anthropic.com`. |
| OpenAI ChatGPT/Codex | Go $8, Plus $20, Pro 5× $100 (Apr 2026), Pro 20× $200, Business ~$25/user; 5h + weekly windows (Plus 5h cap restored 2026-08-25) [3P] | GPT-5.x-Codex / GPT 6 family [3P, unclear] | Codex via ChatGPT login; no standalone API base URL for plan. Closed weights. |
| GitHub Copilot | Pro $10, Pro+ $39, (Max $100 reported), Business $19, Enterprise $39; **usage-based AI Credits since 2026-06-01** (1 credit = $0.01) [O docs + 3P] | Multi-vendor | Copilot API not intended for third-party scripted access. Closed models mostly. |

---

## Summary matrix

| Provider | Plan (entry → top) | Price/mo | Key models (Oct 2026) | Plan base URL (OpenAI-compat) | Official reference base URL | Logprobs on reference | ToS benchmarking risk |
|---|---|---|---|---|---|---|---|
| Z.ai | GLM Coding Lite/Pro/Max | $18 / $80 / $168 (¥118/538/1078) | glm-5.3, glm-5.3-flash (5.2/5.1 aliased → 5.3) | `https://api.z.ai/api/coding/paas/v4` (Anth: `/api/anthropic`) | `https://api.z.ai/api/paas/v4` | No (not documented); `do_sample=false`, thinking toggle yes | **High** (supported tools only; SDK use detected → restricted; ban after 3 violations) |
| Moonshot | Kimi Code Plus/Pro/Max | ¥99 / ¥199 / ¥699 (legacy $19–$199); new subs paused Jul 2026 | k3, k3-256k, kimi-for-coding (K2.8 Preview alias), -highspeed | `https://api.kimi.ai/coding/v1` (CN `api.kimi.com`) | `https://api.moonshot.ai/v1` | **Yes** (top_logprobs ≤20); K3 thinking not disable-able | **Med-High** (UA tampering = violation) |
| MiniMax | M Plan Go/Explore/Build | $22 / $55 / $132 (¥49/119/469) | MiniMax-M3.1-Flash (M2.x routed to it) | `https://api.minimax.io/v1` w/ plan key (Anth `/anthropic`) | `https://api.minimax.io/v1` | Not documented; thinking always on; temp ignored | Med / unknown |
| Alibaba (intl) | Coding Plan Pro (Lite closed) | $50 (¥200) | qwen3.7-plus, qwen3.6-plus, kimi-k2.5, glm-5, MiniMax-M2.5, qwen3.5-plus | `https://coding-intl.dashscope.aliyuncs.com/v1` (Anth `/apps/anthropic`) | Model Studio `https://{ws}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` (Qwen); vendor APIs for GLM/Kimi/MiniMax | Not documented (seed yes, enable_thinking yes) | **High** (explicit ban on automated scripts) |
| Alibaba (CN) | Bailian Token Plan Lite…Pro | ¥39–¥499 | qwen3.8-max/flash, glm-5.3, kimi-k3, deepseek-v4.x | [?] | same | — | High (single device, personal) |
| Volcengine | Ark Coding Plan Lite/Pro | ¥40 / ¥200 | ark-code-latest, Doubao-Seed-2.1, GLM-5.3, Kimi-K3, DeepSeek-V4.x | `https://ark.cn-beijing.volces.com/api/coding/v3` | `https://ark.cn-beijing.volces.com/api/v3` | ? | Unknown |
| Xiaomi | MiMo Token Plan Lite…Max | $6 / $16 / $50 / $100 | mimo-v2.6-pro, -flash, -pro-ultraspeed | `https://token-plan-cn.xiaomimimo.com/v1` (+sgp/ams) | `https://api.xiaomimimo.com/v1` | ? | Low-Med / unknown |
| StepFun | Step Plan Mini…Max | ¥49 / ¥99 / ¥199 / ¥699 | step-5-preview, step-3.7-flash, step-3.5-flash | `https://api.stepfun.ai/step_plan/v1` | `https://api.stepfun.ai/v1` | ? | Unknown |
| Baidu | Qianfan Token Plan (Coding Plan frozen) | ¥9.9–¥600 | DeepSeek-V4, GLM-5.2, Kimi-K2.6, ERNIE 5.1 | ? | ? | ? | Unknown |
| Tencent | Token Plans (Coding Plan discontinued) | ¥28–¥599 | Hy4-preview, GLM-5.3, K3, DeepSeek V4.1 (official + non-official), MiMo-V2.6 | ? | ? | ? | Unknown |
| DeepSeek | — (no plan) | PAYG | deepseek-flash (V4.1), deepseek-v4-pro | — | `https://api.deepseek.com` | **Yes** (≤20); thinking disable-able | n/a |
| OpenCode | Go / Go Plus | $10 / $40 | 29–32 models (GLM-5.3, K3, M3, MiMo, DeepSeek, Qwen…) | `https://opencode.ai/zen/go/v1` (needs `x-opencode-session`) | vendor APIs | — | Med (header requirement) |
| Chutes | Plus / Pro | $10 / $20 | Kimi-K3, GLM-5.2, DeepSeek-V4… (TEE) | `https://llm.chutes.ai/v1` | vendor APIs | — | **High on subs** (automation → PAYG); PAYG fine |
| Synthetic | Go / Standard / Big | $9 / $30 / $90 | hf:moonshotai/Kimi-K3, GLM-5.3, DeepSeek-V4.1-Flash… | `https://api.synthetic.new/openai/v1` | vendor APIs | ? | Unknown (privacy-friendly) |
| Ollama | Pro / Max / Team | $20 / $100 / $500 | kimi-k3, deepseek-v4.1-flash, gpt-oss… (:cloud) | `https://ollama.com/v1` [?] | vendor APIs | — | Low-Med (may use NVFP4 — disclosed) |
| Cerebras | Code Pro / Max (sold out) | $50 / $200 | zai-glm-4.7 | `https://api.cerebras.ai/v1` | `https://api.z.ai/api/paas/v4` | — | Unknown |
| Anthropic | Pro / Max 5× / 20× | $20 / $100 / $200 | Fable 5.1, Opus 5.5, Sonnet 5 | none (Claude Code OAuth only) | `https://api.anthropic.com` | No | **High** (OAuth restricted to Claude Code) |
| OpenAI | Plus / Pro / Pro 20× | $20 / $100 / $200 | GPT Codex models | none | `https://api.openai.com/v1` | Partial | High (ChatGPT login) |
| GitHub | Copilot Pro / Pro+ | $10 / $39 | multi-vendor | none | — | — | High |

## Implications for this project's fidelity harness

1. **ToS:** Alibaba (our current target), Z.ai and Chutes subscriptions explicitly forbid or penalize non-interactive / unsupported-client usage; Kimi forbids UA spoofing. Our `StealthChatClient` UA rotation directly conflicts with Kimi's rule and arguably with Z.ai's "supported tools" rule — worth a deliberate decision (and legal review) before running against those plans. Low call volumes and an honest UA reduce risk but don't remove it.
2. **Model aliasing:** model IDs on plans are routinely aliased to newer/smaller models by policy (Z.ai, MiniMax, Kimi `kimi-for-coding`, Volcengine `ark-code-latest`). Compare plan endpoints against the *aliased-to* reference model, and record the alias target in run metadata.
3. **Logprobs:** only DeepSeek and Moonshot official APIs document `logprobs`/`top_logprobs`. Z.ai, MiniMax, Alibaba (Qwen) do not; plan endpoints almost certainly don't either. Output-distribution tests (arithmetic, entropy, rollout prefix) remain the primary signal.
4. **Thinking/sampling control:** GLM (`thinking:disabled`, `do_sample:false`), DeepSeek (`thinking:disabled`) and Qwen (`enable_thinking:false`) allow non-thinking comparisons; MiniMax M3.x and Kimi K3/K2.7-Code force thinking and fixed sampling, so tests must work at T=1 with sampling-based statistics.
5. **Self-host anchors:** GLM-5.3 (BF16+FP8 on HF, vLLM), MiniMax-M3 (MXFP8 official), MiMo-V2.6 (MIT), DeepSeek V4 Flash/Pro (MIT), Kimi K3 (very large, custom license). Moonshot's Kimi Vendor Verifier (AIME2025 long-output as quantization detector, ToolCall F1) is a ready methodology reference.
6. **Repo staleness:** `benchmarks/providers.json` lists `qwen3-max-2026-01-23` and `qwen3-coder-plus` for the Alibaba plan; the official intl list (updated 2026-10-11) no longer includes them (current: qwen3.7-plus, qwen3.6-plus, kimi-k2.5, glm-5, MiniMax-M2.5, qwen3.5-plus).
