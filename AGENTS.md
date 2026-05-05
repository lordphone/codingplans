# AI Coding Plan Comparison - Agent Guidelines

## Project Overview

A website comparing AI coding plans that monitors whether providers deliver promised performance (throughput, latency, aggressive-quantization detection) against catalog data in Supabase.

## Tech Stack

- **Frontend:** _TBD — being rebuilt from scratch (planned: SvelteKit)._ Will live under `web/`.
- **Database:** Supabase (PostgreSQL + PostgREST)
- **Benchmarks:** Python scripts under `benchmarks/`; CI deploy does **not** run benchmarks (only builds the web app)

## Architecture

```
Web app ──► Supabase DB ◄── GitHub Actions / local scripts (benchmark writers)
```

## Python benchmarks

```bash
python benchmarks/performance/benchmark.py
python benchmarks/performance/check_credentials.py
# fidelity (plan vs vendor reference): python benchmarks/fidelity/model_identity/test_arithmetic.py --help
```

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
subfolders (`model_identity/`, `long_context/`). Each family owns its own
panel data (e.g. `prompts.py` or a programmatic builder) and `runs/`.

Existing references: `benchmarks/fidelity/model_identity/test_arithmetic.py`,
`test_entropy.py`, `test_rollout_prefix.py`,
`benchmarks/fidelity/long_context/test_needle_single.py`,
`test_needle_multi.py`, `test_needle_aggregation.py`, and
`benchmarks/fidelity/compare.py`.

**Run flow (per test, per model):**

1. Run reference once: `python benchmarks/fidelity/model_identity/test_arithmetic.py --endpoint glm5-official` → writes `summary.json` + `.jsonl` under `model_identity/runs/`. Reusable across every plan comparison for the same model.
2. Run each plan target the same way (e.g. `--endpoint glm5-alibaba`). Independent process; can be days apart.
3. Compare offline: `python benchmarks/fidelity/compare.py <ref>.summary.json <target>.summary.json` — no API calls, no `.env` needed. Exit code: `0` pass, `1` fail, `2` error/incompatible.

## Project layout (repo)

```
.
├── .env.example           # template for repo-root .env (benchmarks; not committed secrets)
├── AGENTS.md
├── benchmarks/
│   ├── performance/       # TPS / TTFT (benchmark.py, check_credentials.py, scenarios.py)
│   ├── fidelity/          # model behavior vs reference: model_identity/, long_context/
│   └── providers.json     # benchmark matrix (API keys via env only; tracked)
├── requirements.txt       # Python deps for benchmarks
├── supabase/              # CLI-managed: config.toml, migrations/, seed_*.sql
└── web/                   # _TBD: web app (rebuild in progress)_
```

**Schema changes** live as SQL files under `supabase/migrations/` and are applied via the Supabase CLI (`supabase db push`). The repo is linked to the live project (`supabase/config.toml`), so `supabase migration list` shows local-vs-remote sync.

## Database (Supabase)

**Source of truth:** live Postgres in Supabase. Migrations live in `supabase/migrations/`; apply via `supabase db push`. Regenerate generated DB types after schema changes via `supabase gen types typescript --linked` (wire the script up inside `web/` once the new app is scaffolded).

**Core tables**

| Table            | Role                                                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------- |
| `providers`      | Vendor row; **`slug`** is unique and used in routes                                             |
| `plans`          | Tiers; **`provider_id`** FK; filter **`is_active`** in app                                      |
| `models`         | Catalog model; **`slug`** stable id (e.g. for display/joins)                                    |
| `plan_models`    | M–N plan ↔ model; optional **`usage_limit`** (text)                                             |
| `benchmark_runs` | Time series per `(plan_id, model_id)` — `tps`, `ttft_s`, `aggressively_quantized`, `run_at`     |

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
