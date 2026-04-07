# AI Coding Plan Comparison - Agent Guidelines

## Project Overview

A website comparing AI coding plans that monitors whether providers deliver promised performance (throughput, latency, quantization labels) against catalog data in Supabase.

## Tech Stack

- **Frontend:** Angular 21 (standalone components), Tailwind CSS 4, **Vitest** via `ng test`
- **SSR:** `@angular/ssr` with `app.routes.server.ts`: **`/`** and **`/directory`** are **prerendered**; nested directory routes, **`/benchmarks`**, and **`/models`** use **server** rendering. `main.server.ts`, `server.ts`, and `app.config.server.ts` wire the Node bundle; local `npm run serve:ssr:coding-plans` runs `dist/coding-plans/server/server.mjs` (Express 5).
- **Database:** Supabase (PostgreSQL + PostgREST)
- **Benchmarks:** Python scripts under `benchmarks/`; CI deploy does **not** run benchmarks (only builds the web app)

## Architecture

```
Angular ──► Supabase DB ◄── GitHub Actions / local scripts (benchmark writers)
```

## Build & test (web)

```bash
cd web
npm install
npm start              # alias: ng serve — dev server
npm run build          # production build (browser + SSR artifacts)
npm test               # ng test — Vitest
npm run serve:ssr:coding-plans   # run SSR output after build (see package.json)
```

**GitHub Pages:** `.github/workflows/deploy.yml` runs on push to `main` (and `workflow_dispatch`) with **Node 24**, `npm ci` in `web/`, then  
`npm run build -- --configuration=production --base-href=/codingplans/`  
and uploads **`web/dist/coding-plans/browser`** only (static hosting; the SSR server is not deployed there).

The repo root has a minimal `package-lock.json`; **application dependencies** live under **`web/package-lock.json`**.

## Python benchmarks

```bash
python benchmarks/performance/benchmark_tps.py --config benchmarks/providers.json
```

Use `benchmarks/providers.example.json` as a template; real `providers.json` is gitignored.

## Project layout (repo)

```
.
├── .github/workflows/     # e.g. deploy.yml → GitHub Pages
├── AGENTS.md
├── benchmarks/
│   ├── performance/       # TPS / TTFT scripts (e.g. benchmark_tps.py, scenarios.py)
│   ├── quantize/          # e.g. benchmark_quantize.py
│   ├── providers.json     # gitignored
│   └── providers.example.json
├── requirements.txt       # Python deps for benchmarks
└── web/                   # Angular app (project name: coding-plans)
    ├── package.json
    ├── angular.json
    └── src/
        ├── app/
        │   ├── app.config.ts
        │   ├── app.config.server.ts
        │   ├── app.routes.ts
        │   ├── app.routes.server.ts
        │   ├── components/layout/     # shell: top nav + router-outlet
        │   ├── pages/
        │   │   ├── directory/         # Supabase-backed comparison table
        │   │   ├── plan/              # per-plan performance (charts, model tabs)
        │   │   ├── provider/          # Supabase-backed provider overview
        │   │   ├── benchmarks/        # placeholder (“Benchmark Explorer”)
        │   │   └── models/            # placeholder (lazy-loaded)
        │   ├── services/
        │   │   ├── supabase.service.ts
        │   │   └── directory-snapshot.service.ts   # in-memory last directory load for plan shell
        │   ├── types/database.types.ts
        │   └── version.ts           # APP_VERSION from package.json → nav
        └── environments/
```

There is **no** `supabase/` migrations folder in the repo; schema changes are applied in the Supabase project (SQL Editor / dashboard).

## Environment (Supabase client)

- **`web/src/environments/environment.ts`** (and `environment.prod.ts`): `supabaseUrl` + **anon / publishable** key for browser reads. This is expected to be public for read-only directory data.
- **Never** commit the **service role** key or provider API secrets. Use env vars locally and in CI for writes (benchmarks, admin scripts).

## Database (Supabase)

**Source of truth:** live Postgres in Supabase. Regenerate types when schema changes: `supabase gen types typescript` (CLI), then reconcile `web/src/app/types/database.types.ts`.

**Core tables**

| Table | Role |
|-------|------|
| `providers` | Vendor row; **`slug`** is unique and used in routes |
| `plans` | Tiers; **`provider_id`** FK; filter **`is_active`** in app |
| `models` | Catalog model; **`slug`** stable id (e.g. for display/joins) |
| `plan_models` | M–N plan ↔ model; optional **`usage_limit`** (text) |
| `benchmark_runs` | Time series per `(plan_id, model_id)` — `tps`, `ttft_s`, `quantization`, `run_at` |

**Plan slugs** are **not** globally unique across providers (e.g. multiple `lite` / `pro`). Prefer **prefixed** slugs (`xiaomi-lite`, …) when inserting data to keep URLs unambiguous. Routes use **`providers.slug`** and **`plans.slug`** as stored in the DB.

**Directory query (`SupabaseService.fetchDirectoryFromSupabase`):**

1. Nested select: `providers` → `plans` → `plan_models` → `models` (active plans only).
2. Second query: `benchmark_runs` for those `plan_id`s — **TPS/TTFT:** rolling **7-day** averages; **quantization:** latest non-null row per `(plan_id, model_id)` (any time).
3. PostgREST embed result is cast `as unknown as ProviderWithPlansAndModels[]` for TypeScript.

**Provider page (`fetchProviderPageFromSupabase`):** same nested provider/plan/model shape and the **same 7-day / latest-quant** benchmark rules as the directory, formatted for the provider overview UI.

**Plan performance page (`fetchPlanPerformancePage`):** resolves plan by `provider.slug` + `plans.slug`; loads `benchmark_runs` for the last **`PLAN_PAGE_BENCHMARK_DAYS` (30)** days, with daily buckets for TPS/TTFT series and individual quantization runs per model.

**Client routing IDs:** `DirectoryProvider.id` and `DirectoryPlan.id` in the UI are the DB **`slug`** values (not UUIDs), matching URL segments.

**Usage limits:** `plan_models.usage_limit` is mapped to a placeholder label in code (`USAGE_PLACEHOLDER`); the directory shows that placeholder until real limits are surfaced.

**`DirectorySnapshotService`:** after a successful directory load, keeps the listing in memory so **`PlanComponent`** can render header/model tabs immediately on in-app navigation while `fetchPlanPerformancePage` loads chart data.

**RLS:** `anon` can **SELECT** public directory data. **Inserts/updates** (benchmarks, manual seeding) need the **service role** or a privileged path — not the anon key.

### Benchmarks vs directory naming

| Concept | What it is |
|---------|------------|
| `benchmark_runs.model_id` | UUID → `models.id` |
| `models.slug` | Catalog / display id (`kimi-k2.5`, …) |
| `providers.json` → `models[]` | **API** `model` string for the vendor HTTP request — may differ from `models.slug` |

When writing benchmark rows, resolve API model name → `models.id`.

## Directory page (behavior)

- **Title:** “Provider & Plan Directory” (no subtitle line under the H1).
- **Table columns:** Tier · Model · Quantization · Performance (TPS bar + TTFT) · Usage limits · Cost.
- **State:** `signals` + `computed` view model; search filters rows client-side (provider name/slug, plan name/slug, model name, quantization text, usage label).
- **Quantization UI:** `QuantizationStatus` = `scam` \| `verified` \| `untested` (see `directory.models.ts`); inferred from benchmark label + heuristics in `supabase.service.ts`. Rows can show a **“Loss Detected”** line when status is scam and the label mentions scam/reset-style wording (see `showsQuantizationLossNotice` in `directory.component.ts`).
- **Deep links:** tier and model cells link to `/directory/:providerSlug/:planSlug/:modelSlug`.

## Plan page (`PlanComponent`)

- **Route:** `/directory/:providerId/:planId` with optional **`/:modelSlug`** (param names are historical; values are **slugs**).
- **Data:** Supabase `fetchPlanPerformancePage`; shell metadata can be hydrated from **`DirectorySnapshotService`** when navigating from the directory.
- **UI:** Model tabs, TPS/TTFT sparklines over the configured window, quantization run list (see `plan.component.ts` / `plan.models.ts`).

## Security

- Do not commit **service role** keys, provider API keys, or secrets.
- Use environment variables for benchmark configs and CI secrets.

## Git conventions

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Prefer small, focused commits

## UI shell

- **Layout:** Fixed top nav — brand link, **`v{{ appVersion }}`** from `web/src/app/version.ts` (`package.json` version), links **DIRECTORY** and **BENCHMARKS** only. No sidebar filter rails.
- **`/models`** is routed but **not** linked in the nav (lazy-loaded placeholder).

## Sitemap

| Path | Purpose |
|------|---------|
| `/` | Redirects to `/directory` |
| `/directory` | Comparison table + search |
| `/directory/:providerId` | Provider page (`ProviderComponent`) — **Supabase** |
| `/directory/:providerId/:planId` | Plan performance page (`PlanComponent`) |
| `/directory/:providerId/:planId/:modelSlug` | Same plan page; **modelSlug** selects the active model tab |
| `/benchmarks` | Placeholder (“Benchmark Explorer”) |
| `/models` | Placeholder (not in main nav) |

**Example URL segments** (must match DB slugs):

- `/directory/alibaba-cloud-model-studio-coding-plan`
- `/directory/alibaba-cloud-model-studio-coding-plan/lite`
- `/directory/alibaba-cloud-model-studio-coding-plan/lite/some-model-slug`
