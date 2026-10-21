# What you need to run the audit

Everything the pipeline needs, in the order you'll set it up. Nothing here is
optional except the extra providers. You can start with a single plan and add
more later. A group runs as soon as both of its keys exist; groups without keys
are skipped with a log line.

> **Read §0 first.** Several plans' terms of service forbid exactly this kind of
> automated use. That is a decision for you to make, not a technical detail.

---

## 0. Terms-of-service risk (decide before you buy anything)

From the provider research (`docs/research/landscape.md`, snapshot 2026-10-20):

| Plan | What the terms say | Risk |
|---|---|---|
| **Alibaba Model Studio Coding Plan** | "Do not use the plan's API key for automated scripts, application backends, or other non-interactive scenarios." Violations lead to suspension or key revocation. | **High.** Every `*-alibaba` endpoint, including the existing `glm5-alibaba`, falls in the prohibited category. |
| **Z.ai GLM Coding Plan** | Use is "strictly limited to officially supported tools". Detected SDK use may restrict benefits, and more than 3 violations may lead to a ban. | **High.** |
| **Kimi Code** (Moonshot) | "Tampering with the client identifier (User-Agent) is treated as a violation." | **Medium–high.** `kimi-k3-kimi-code` is therefore flagged `honest_user_agent: true`: it sends `codingplans-audit/1.0`, not a rotated IDE UA. |
| **MiniMax M Plan** | No explicit automation ban found. | Medium / unknown. |
| **Chutes** subscriptions | Automated workloads must use pay-as-you-go. | High (not configured). |

Practical consequences:

- **The account can be banned.** The `StealthChatClient`'s rotated IDE User-Agents and jittered pacing make the traffic *look* like a developer. They do not make it *allowed*. Use a plan account you can afford to lose.
- **Keep volume low.** The `quick` tier is about 300 calls per endpoint per day, well under any plan's 5-hour window. The `full` tier is about 4,000 calls, so run it rarely.
- **Ask the vendor if you want a durable setup.** Some vendors run their own verifier programs (Moonshot's Kimi Vendor Verifier) and may grant audit access.

---

## 1. API keys

You need **two keys per audited model**: one for the **official pay-as-you-go API** (the reference) and one for the **coding plan** (the target). One official key serves every plan that resells the same model; for example, a single Z.ai key is the reference for both the GLM-5 Alibaba audit and the GLM-5.3 Z.ai-plan audit.

All names below are the exact environment variable names. They go in the repo-root `.env` locally (copy `.env.example`) and in **GitHub → Settings → Secrets and variables → Actions → Secrets** for CI.

### Official references (pay-as-you-go, billed per token)

| Env var | Where to get it | Used by endpoints | Notes |
|---|---|---|---|
| `ZAI_API_KEY` | z.ai → API platform → API keys (**PAYG** key; plan keys are a separate category) | `glm5-official`, `glm53-official` | Load ~$10 credit. |
| `MOONSHOT_API_KEY` | platform.moonshot.ai (intl) → API keys | `kimi-k2.5-official`, `kimi-k3-official` | Supports `logprobs` (future logprob tests). |
| `MINIMAX_API_KEY` | platform.minimax.io → API keys (PAYG) | `minimax-m2.5-official`, `minimax-m31-official` | M2.5 retires 2026-11-18. |
| `DASHSCOPE_API_KEY` | Alibaba Cloud Model Studio (intl, Singapore) → API keys (`sk-…`, **not** the `sk-sp-…` plan key) | `qwen36-plus-official` | Region-specific; newer accounts may need the `{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com` URL. Set `QWEN36_PLUS_OFFICIAL_BASE_URL`. |

### Coding plans (flat-rate subscriptions, the things being audited)

| Env var | Plan to buy | Price (snapshot) | Endpoints |
|---|---|---|---|
| `ALIBABA_CLOUD_MODEL_STUDIO_CODING_PLAN_API_KEY` | Alibaba Model Studio **Coding Plan Pro** (intl). Key starts `sk-sp-`. | $50/mo | `glm5-alibaba`, `kimi-k2.5-alibaba`, `minimax-m2.5-alibaba`, `qwen36-plus-alibaba` |
| `ZAI_CODING_PLAN_API_KEY` | Z.ai **GLM Coding Plan** (Lite is enough for audits) | $18 / $80 / $168 | `glm53-zai-coding` |
| `KIMI_CODE_API_KEY` | Kimi membership with **Kimi Code** (new subscriptions were paused July 2026; check availability) | ¥99 / ¥199 / ¥699 | `kimi-k3-kimi-code` |
| `MINIMAX_M_PLAN_API_KEY` | MiniMax **M Plan** (Go is enough) | $22 / $55 / $132 | `minimax-m31-mplan` |

**Cheapest useful start:** `ZAI_API_KEY` plus `ZAI_CODING_PLAN_API_KEY` (Lite). That is one model and one plan for about $18/mo plus a few dollars of PAYG. The Alibaba plan alone covers four models at $50/mo, but has the strictest ToS.

**Rough reference cost per audit** (official side; plan side is flat-rate): `quick` ≈ 300 calls ≈ $0.30–$1 per model. `standard` adds coding, reasoning and arithmetic, about 1,400 calls ≈ $3–$8 per model, with reasoning tokens dominating. References are reused for 7 days, so this cost is paid once a week per model, not once per plan.

---

## 2. Supabase (stores results; the site reads them)

The project the old site pointed at (`htuflimuceuwjldkupnx.supabase.co`) **no longer resolves in DNS** (checked 2026-10-20). It was probably paused or deleted, so plan on a new project:

1. Create a project at supabase.com (free tier is fine).
2. Link and push the schema from the repo root:
   ```bash
   supabase link --project-ref <new-ref>
   supabase db push            # applies supabase/migrations/* (baseline + audit_results)
   ```
3. Load the catalog (providers, plans, models), using the SQL editor or psql:
   ```bash
   psql "$SUPABASE_DB_URL" -f supabase/seed.sql
   ```
4. Copy three values from **Project Settings → API**:

| Value | Put it in | Secret? |
|---|---|---|
| Project URL `https://<ref>.supabase.co` | `SUPABASE_URL` (Actions **secret**, and `.env`) **and** `PUBLIC_SUPABASE_URL` (Actions **variable**) | URL is public |
| `anon` / publishable key | `PUBLIC_SUPABASE_ANON_KEY` (Actions **variable**) | Public by design (RLS = read-only) |
| `service_role` key | `SUPABASE_SERVICE_ROLE_KEY` (Actions **secret**, and `.env`) | **Secret.** Bypasses RLS; never put it in `web/`. |

---

## 3. GitHub repository settings

- **Pages:** Settings → Pages → Source: **GitHub Actions**. The site deploys to `https://lordphone.github.io/codingplans/`.
- **Actions secrets:** every key in §1 that you have, plus `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
- **Actions variables:** `PUBLIC_SUPABASE_URL`, `PUBLIC_SUPABASE_ANON_KEY`.
- The `Audit plans` workflow runs on a schedule as soon as it is on `main`: speed probes 4×/day, the `quick` tier daily, and `standard` on Sundays. Each completed run triggers `Deploy site`. Disable the workflow in the Actions tab if you want to hold off.

---

## 4. Local tooling

| Tool | Version | Why |
|---|---|---|
| Python | ≥ 3.11 (CI uses 3.12) | benchmarks |
| `pip install -r requirements.txt` | httpx, python-dotenv | |
| Node | ≥ 22 (CI uses 24) | web app |
| Supabase CLI | any 2.x | migrations |
| Docker or another container runtime | optional | `code_exec` runs model-written code; the sandbox does **not** block network access, so run that test in CI or a container rather than on your laptop |

---

## 5. First run, in order

```bash
cp .env.example .env                                         # fill in the keys you have
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python benchmarks/selftest.py --e2e                # offline; must say ALL CHECKS PASSED
.venv/bin/python benchmarks/audit/preflight.py               # one tiny call per endpoint with a key
```

Read the preflight output and fix `benchmarks/endpoints.json` (or set `<SLUG>_MODEL` / `<SLUG>_BASE_URL`) until every endpoint you care about says `ok`. Watch for these three:

- `served_model`: if it differs from the requested model id, the provider is aliasing. That is worth knowing in itself.
- `usage=NO`: `token_accounting` will be inconclusive for that endpoint.
- `tools: NO tool call returned`: the endpoint may not support `tools` on the OpenAI-compatible path.

Then flip `"verified": true` on endpoints that check out, and run:

```bash
.venv/bin/python benchmarks/audit/run_audit.py --dry-run                     # shows the plan and which keys are missing
.venv/bin/python benchmarks/audit/run_audit.py --group glm-5.3 --tier quick  # ~300 calls per endpoint
.venv/bin/python benchmarks/audit/run_audit.py --group glm-5.3 --tier quick --ingest
.venv/bin/python benchmarks/audit/run_performance.py --samples 5 --ingest
```

Reports land in `benchmarks/audit/reports/`, and raw artifacts in each family's `runs/`. Both are git-ignored.

---

## 6. Things that are unverified (fix as you go)

- **Model ids and URLs.** Every model id and base URL in `endpoints.json` comes from vendor docs or third-party pages (`verified: false`). They have not been called. In particular: the Kimi Code model id (`k3`), the MiniMax plan key and host mapping, and whether Alibaba's plan accepts `enable_thinking` for GLM and Kimi models.
- **Prices and limits.** The figures in `supabase/seed.sql` are from the research snapshot. Several are third-party sourced and change monthly.
- **Fail thresholds.** Every comparator threshold is an informed prior, not calibrated. The research recommends running **official vs official** (the same reference endpoint twice) for each test and checking that it passes. Do that once per model before trusting a `fail`.
- **Forced-thinking models.** Kimi K3 and MiniMax M3.x cannot disable thinking and ignore temperature, so the T=0 weight tests (`arithmetic`, `rollout_prefix`, needles) are skipped for them automatically.
