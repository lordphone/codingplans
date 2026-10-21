# AI Coding Plan Comparison - Agent Guidelines

## Project Overview

A website comparing AI coding plans that monitors whether providers deliver promised performance (throughput, latency, aggressive-quantization detection) against catalog data in Supabase.

## Tech Stack

- **Frontend:** **SvelteKit** with **Svelte 5 (runes mode)**, **TypeScript**, **Tailwind CSS 4**. Lives under `web/`. Routes: `/` (directory), `/providers/[provider]/`, `/providers/[provider]/[plan]/`, `/benchmarks/`, `/methodology/`.
- **Deploy:** `@sveltejs/adapter-static` → GitHub Pages (static prerendered HTML, `404.html` fallback, `static/.nojekyll`). `kit.paths.base` comes from `BASE_PATH` (CI sets `BASE_PATH=/codingplans`; unset → domain root). Use `resolve()` from `$app/paths` for every internal link.
- **Database:** Supabase (PostgreSQL + PostgREST), read with `@supabase/supabase-js` **at build time only** (server `load` functions during prerender) using the public anon key. The browser never talks to Supabase.
- **Benchmarks:** Python scripts under `benchmarks/`. The `Deploy site` workflow only builds the web app; the separate `Audit plans` workflow (`.github/workflows/audit.yml`) runs scheduled audits/speed probes, ingests into Supabase, and triggers a redeploy.
- **Design system:** See `DESIGN.md` (Stitch spec — colors, typography, chart tokens). The `colors` / `typography` maps there are the source of truth and must stay aligned with the Tailwind `@theme` block in `web/src/app.css` (which also defines the dark-mode values).
- **Tooling:** `prettier`, `eslint`, `npm`. No unit-test framework wired in yet.

### Svelte 5

This project uses **Svelte 5 in runes mode**. Refer to the official docs at svelte.dev/docs/svelte for current syntax and APIs.

## Architecture

```
SvelteKit (web/) ──► Supabase DB ◄── GitHub Actions / local scripts (benchmark writers)
```

## Frontend (web/)

All `npm` scripts run from inside `web/`:

```bash
cd web/
npm install
npm run dev        # vite dev server (reads web/.env if present)
npm run build      # static build via adapter-static → web/build
npm run preview    # serve the production build locally (set the same BASE_PATH as the build)
npm run check      # svelte-kit sync + svelte-check (type/diagnostics)
npm run lint       # prettier --check . && eslint .
npm run format     # prettier --write .

PUBLIC_DATA_SOURCE=fixtures BASE_PATH=/codingplans npm run build   # sample data, GH Pages paths
```

**Build-time env** (all public; template in `web/.env.example`):

| Variable                   | Effect                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------- |
| `PUBLIC_SUPABASE_URL`      | Supabase project URL                                                                    |
| `PUBLIC_SUPABASE_ANON_KEY` | anon / publishable key (SELECT-only via RLS)                                            |
| `PUBLIC_DATA_SOURCE`       | `fixtures` → build from `src/lib/data/fixtures.ts` and show a "Sample data" banner      |
| `BASE_PATH`                | path prefix (`/codingplans` on GitHub Pages)                                            |

Without Supabase vars (and not in fixtures mode) the build succeeds with "No measurements published yet" empty states. **Any Supabase error during the build fails the build** — an empty site is never published silently.

**Layout:**

- `src/lib/data/` — all data access. `index.server.ts` (`loadDirectory()`, memoised per build; the only module pages import), `supabase.server.ts` (paged PostgREST reads), `fixtures.ts` (deterministic sample data), `shape.ts` (pure rows → view models; implements the directory semantics below), `types.ts` (hand-written row types + view models; swap for `supabase gen types` later).
- `src/lib/components/` — UI primitives (StatusBadge, StatTile, SortHeader, TableCard, LineChart, BarMini, AuditTable, ModelMetricsTable, Banner, ThemeToggle, SiteNav, SiteFooter, …).
- `src/lib/content/tests.ts` — methodology test catalogue (`TESTS`); ids match `audit_results.test_name` and are the `/methodology/#<id>` anchors.
- `src/app.css` — Tailwind entry + `@theme` tokens (mirror `DESIGN.md`), dark-mode overrides, typography utilities.
- Every page is prerendered (`prerender = true`, `trailingSlash = 'always'` in `src/routes/+layout.ts`); dynamic routes export `entries()` from the loaded directory.

**Integrity verdict** per (plan, model) and per plan, from `latest_audit_results`: any `fail` → Flagged; all `pass` (≥1) → Verified; no rows → Untested; otherwise Partial.

No unit-test runner is wired in; `npm run check` is the only automated correctness gate today.

## Python benchmarks

```bash
python benchmarks/performance/benchmark.py
python benchmarks/performance/check_credentials.py
# fidelity (plan vs vendor reference): python benchmarks/fidelity/model_identity/test_arithmetic.py --help
```

### Audit pipeline (preferred entry point)

```bash
python benchmarks/selftest.py --e2e                               # offline: unit checks + full pipeline vs a fake API
python benchmarks/audit/preflight.py                              # one tiny call per endpoint with a key
python benchmarks/audit/run_audit.py --dry-run                    # plan + missing keys
python benchmarks/audit/run_audit.py --group glm-5 --tier quick [--ingest]
python benchmarks/audit/run_audit.py --group glm-5 --tier quick --calibrate   # official vs official
python benchmarks/audit/run_performance.py --samples 5 [--ingest]
```

**`benchmarks/endpoints.json`** is the single endpoint registry (base URL, key env, model id, thinking on/off params, `honest_user_agent`, `verified`) plus the `audits` groups (which plan endpoints are compared against which official reference, and their DB `provider_slug`/`plan_slug`/`model_slug`). `fidelity/targets.py` loads it. Tiers (`quick`/`standard`/`full`) and the CLI/headline adapters for every test live in `benchmarks/audit/registry.py`. Everything needed to run for real — keys per provider, Supabase, GitHub settings, ToS caveats — is in **`docs/REQUIREMENTS.md`**. Research behind the test choices: `docs/research/`.

Env overrides used by tests/CI: `CODINGPLANS_ENDPOINTS_JSON`, `CODINGPLANS_RUNS_ROOT`, `CODINGPLANS_REPORTS_DIR`, and per-endpoint `<SLUG>_BASE_URL` / `<SLUG>_MODEL`.

### Legacy performance script

Reads **`benchmarks/providers.json`** (tracked in git): provider slug, API base URL, `api_key_env`, and model ids. Workload text comes from **`benchmarks/performance/scenarios.py`**, not this file. API keys stay in **`.env`** or CI secrets. Use **`check_credentials.py`** to confirm keys are loaded from `.env` without pasting them into `curl`.

Copy `.env.example` → `.env` for local secrets (`ALIBABA_CLOUD_MODEL_STUDIO_CODING_PLAN_API_KEY`, `ZAI_API_KEY`, etc.); `.env` is gitignored.

## Fidelity test structure (mandatory for new tests)

Every test under `benchmarks/fidelity/` follows this shape so runs are
reusable across many provider comparisons (e.g. one official z.ai run feeds
all 5 GLM-5 plan audits):

1. **Single-endpoint runner.** `run_<test>(endpoint, *, panel, n_samples, max_tokens, schedule_seed, sleep_range, …) -> (RunResult, raw_rows)`. Hits exactly one endpoint. No `target`/`reference` distinction; that lives in the comparison step only.
2. **Self-describing artifact.** Each run writes `<stamp>_<endpoint_label>_<test>.summary.json` (a serialized `RunResult` from `fidelity/framework.py`) plus a `.jsonl` per-call forensic log. The summary carries `schema_version`, `panel_id`, `panel_size`, `prompt_hash`, `n_samples`, `max_tokens`, `schedule_seed`, `sleep_range_s`, endpoint metadata, and per-prompt outcomes.
3. **Compare = pure function.** `compare_<test>(reference, target) -> Report`. No HTTP, no env, no I/O. Calls `assert_comparable()` (in `fidelity/framework.py`) which refuses to compare runs with mismatched `schema_version`, `test_name`, `panel_id`, `panel_size`, `prompt_hash`, `n_samples`, or `max_tokens`. Sleep range and schedule seed are stealth knobs and **do not** affect comparability.
4. **CLI.** Each `test_*.py` takes `--endpoint <slug>` (slug from `targets.ENDPOINTS`), runs once, writes artifacts to its family's `runs/` (e.g. `model_identity/runs/`). The shared `fidelity/compare.py` joins any two artifacts.
5. **Stealth.** Use `StealthChatClient` (rotated UA, jittered pacing) and a shuffled `make_schedule`. No batch APIs, ever.
6. **Panel versioning.** Each family keeps its own `prompts.py` (e.g. `model_identity/prompts.py`). Bump the `_v1` suffix on `*_PANEL_ID` whenever prompt content changes — that invalidates old artifacts via `prompt_hash` and `panel_id` mismatch checks.

**Layout** — shared plumbing at `benchmarks/fidelity/` (`client.py`,
`targets.py`, `framework.py`, `compare.py`); family-specific data and drivers in
subfolders (`model_identity/`, `long_context/`, `agentic/`, `integrity/`,
`reasoning/`, `coding/`). Panel module names must be unique across families
(`compare.py` puts every family on `sys.path`) — hence `tool_prompts.py`,
`integrity_prompts.py`, etc. Each family owns its own
panel data (e.g. `prompts.py` or a programmatic builder) and `runs/`.

Existing references: `benchmarks/fidelity/model_identity/test_arithmetic.py`,
`test_entropy.py`, `test_rollout_prefix.py`,
`benchmarks/fidelity/long_context/test_needle_single.py`,
`test_needle_multi.py`, `test_needle_aggregation.py`, and the newer
`run_panel` / `standard_cli`-based tests (`agentic/test_tool_calls.py`,
`integrity/test_*.py`, `reasoning/test_reasoning_budget.py`,
`coding/test_code_exec.py`), whose reports also expose a uniform headline
(`metric`, `reference_value`, `target_value`, `p_value`, `inconclusive`,
`fail`). New tests must be registered in `compare.py` and
`audit/registry.py`, and get honest/cheating cases in `selftest.py`; and
`benchmarks/fidelity/compare.py`.

**Design context:** `benchmarks/fidelity/IMPROVEMENTS.md` (rationale behind the signal-to-noise tightening) and `benchmarks/fidelity/THREATS.md` (adversarial model for stealth knobs) are required reading before changing test contracts or the framework.

**Adding a benchmark endpoint:** see the module docstring in `benchmarks/fidelity/targets.py` — it covers slug conventions and the `<SLUG>_BASE_URL` / `<SLUG>_API_KEY_ENV` override pattern.

**Run artifacts** under each family's `runs/` directory are local-only; only a `.gitkeep` is tracked. Don't commit `.summary.json` / `.jsonl` outputs.

**Run flow (per test, per model):**

1. Run reference once: `python benchmarks/fidelity/model_identity/test_arithmetic.py --endpoint glm5-official` → writes `summary.json` + `.jsonl` under `model_identity/runs/`. Reusable across every plan comparison for the same model.
2. Run each plan target the same way (e.g. `--endpoint glm5-alibaba`). Independent process; can be days apart.
3. Compare offline: `python benchmarks/fidelity/compare.py <ref>.summary.json <target>.summary.json` — no API calls, no `.env` needed. Exit code: `0` pass, `1` fail, `2` error/incompatible.

## Project layout (repo)

```
.
├── .env.example           # template for repo-root .env (benchmarks; not committed secrets)
├── .github/workflows/     # deploy.yml (site → Pages), audit.yml (scheduled audits + speed probes)
├── AGENTS.md
├── benchmarks/
│   ├── audit/             # orchestrator: run_audit.py, run_performance.py, preflight.py, ingest.py, registry.py
│   ├── performance/       # TPS / TTFT primitives (benchmark.py, check_credentials.py, scenarios.py)
│   ├── fidelity/          # tests vs reference: model_identity/, long_context/, agentic/, integrity/, reasoning/, coding/
│   ├── endpoints.json     # endpoint registry + audit groups (tracked; keys via env only)
│   ├── providers.json     # legacy matrix for performance/benchmark.py
│   └── selftest.py        # offline checks + e2e against a fake API
├── docs/                  # REQUIREMENTS.md (keys/setup/ToS), research/
├── requirements.txt       # Python deps for benchmarks
├── supabase/              # CLI-managed: config.toml, migrations/, seed.sql (catalog)
└── web/                   # SvelteKit app (prerendered from Supabase at build time)
```

## Database (Supabase)

**Source of truth:** `supabase/migrations/` (the baseline migration reconstructs the originally hand-made tables, so a fresh project can be built from the repo). Catalog rows live in `supabase/seed.sql`. As of 2026-10-20 the previously linked project (`htuflimuceuwjldkupnx`) no longer resolves and `supabase link` was never run in this checkout — see `docs/REQUIREMENTS.md` §2.

**Common Supabase CLI ops** (run from repo root):

```bash
supabase migration list                       # compare local migrations vs remote
supabase db push                              # apply pending migrations to the linked project
supabase gen types typescript --linked        # regenerate DB types (wire into web/ once stable)
```

The directory-query semantics below are implemented in `web/src/lib/data/shape.ts` (fed by `supabase.server.ts`); keep the two in sync.

**Core tables**

| Table            | Role                                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------- |
| `providers`      | Vendor row; **`slug`** is unique and used in routes                                             |
| `plans`          | Tiers; **`provider_id`** FK; filter **`is_active`** in app                                      |
| `models`         | Catalog model; **`slug`** stable id (e.g. for display/joins)                                    |
| `plan_models`    | M–N plan ↔ model; optional **`usage_limit`** (text)                                             |
| `benchmark_runs` | Time series per `(plan_id, model_id)` — `tps`, `ttft_s`, `tps_p10`, `ttft_p90_s`, `error_rate`, `samples`, `aggressively_quantized`, `run_at` |
| `audit_results`  | One row per `(plan, model, test, run)` — `status` pass/fail/inconclusive/error, headline `metric` + reference/target values, `p_value`/`q_value` (BH), `summary`, `details` jsonb. View `latest_audit_results` = newest per test. |

**Plan slugs** are **not** globally unique across providers (e.g. multiple `lite` / `pro`). Prefer **prefixed** slugs (`xiaomi-lite`, …) when inserting data to keep URLs unambiguous. Routes use **`providers.slug`** and **`plans.slug`** as stored in the DB.

**Directory query semantics** (any new client should match these to keep numbers consistent):

1. Nested select: `providers` → `plans` → `plan_models` → `models` (active plans only).
2. Benchmark queries for those `plan_id`s — **TPS/TTFT:** rolling **30-day** window averages; **quantization status:** latest non-null `aggressively_quantized` per `(plan_id, model_id)` (any time).
3. **Quantization mapping:** `aggressively_quantized` (`true` → aggressive, `false` → standard, `null`/no rows → untested) — no string-label inference.
4. **Usage limits:** `plan_models.usage_limit` is currently surfaced as a placeholder label until real limits are wired in.
5. **Routing IDs:** UI route segments are DB **slugs** (not UUIDs).

**RLS:** `anon` can **SELECT** public directory data. **Inserts/updates** (benchmarks, manual seeding) need the **service role** or a privileged path — not the anon key.

### Benchmarks vs directory naming

| Concept                       | What it is                                                                         |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `benchmark_runs.model_id`     | UUID → `models.id`                                                                 |
| `models.slug`                 | Catalog / display id (`kimi-k2.5`, …)                                              |
| `providers.json` → `models[]` | **API** `model` string for the vendor HTTP request — may differ from `models.slug` |

When writing benchmark rows, resolve API model name → `models.id`.

## Security

- Do not commit **service role** keys, provider API keys, or secrets.
- Use environment variables for benchmark configs and CI secrets.
- The browser-side Supabase **anon / publishable** key is expected to be public for read-only directory data; never ship the **service role** key in client code.

## Git conventions

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Prefer small, focused commits

## Repo conventions

- `CLAUDE.md` is a symlink → `AGENTS.md` (single source of truth). Edit `AGENTS.md`; if the symlink ever gets clobbered, restore it with `ln -sf AGENTS.md CLAUDE.md`.
