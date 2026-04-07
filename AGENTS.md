# AI Coding Plan Comparison - Agent Guidelines

## Project Overview

A website comparing AI coding plans that monitors whether providers deliver promised performance (throughput, latency, quantization labels) against catalog data in Supabase.

## Tech Stack

- **Frontend:** Angular 21 (standalone components), Tailwind CSS 4, **Vitest** via `ng test`
- **SSR:** `@angular/ssr` is configured (`main.server.ts`, `server.ts`); local `npm run serve:ssr:coding-plans` serves the Node bundle
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

**GitHub Pages:** `.github/workflows/deploy.yml` builds on push to `main` with  
`npm run build -- --configuration=production --base-href=/codingplans/`  
and uploads **`web/dist/coding-plans/browser`** only (static hosting; SSR server is not deployed there).

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
│   ├── performance/       # TPS / TTFT scripts
│   ├── quantize/
│   ├── providers.json     # gitignored
│   └── providers.example.json
├── requirements.txt       # Python deps for benchmarks
└── web/                   # Angular app (project name: coding-plans)
    ├── package.json
    ├── angular.json
    └── src/
        ├── app/
        │   ├── app.config.ts
        │   ├── app.routes.ts
        │   ├── components/layout/     # shell: top nav + router-outlet
        │   ├── pages/
        │   │   ├── directory/       # Supabase-backed comparison table
        │   │   ├── provider/ # mock / static for now
        │   │   ├── benchmarks/
        │   │   └── models/
        │   ├── services/supabase.service.ts
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

**Usage limits:** `plan_models.usage_limit` exists in types/DB but is **not** selected in the directory query; the UI shows **—** for every row until wired up.

**RLS:** `anon` can **SELECT** public directory data. **Inserts/updates** (benchmarks, manual seeding) need the **service role** or a privileged path — not the anon key.

### Benchmarks vs directory naming

| Concept | What it is |
|---------|------------|
| `benchmark_runs.model_id` | UUID → `models.id` |
| `models.slug` | Catalog / display id (`kimi-k2.5`, …) |
| `providers.json` → `models[]` | **API** `model` string for the vendor HTTP request — may differ from `models.slug` |

When writing benchmark rows, resolve API model name → `models.id`.

## Directory page (behavior)

- **Title:** “Provider & Plan Directory” (no subtitle line).
- **Table columns:** Tier · Model · Quantization · Performance (TPS bar + TTFT) · Usage limits · Cost.
- **State:** `signals` + `computed` view model; search filters rows client-side (provider name/slug, plan name/slug, model name, quantization text, usage label).
- **Quantization UI:** `QuantizationStatus` = `scam` \| `verified` \| `untested` (see `directory.models.ts`); inferred from benchmark label + heuristics in `supabase.service.ts`.

## Security

- Do not commit **service role** keys, provider API keys, or secrets.
- Use environment variables for benchmark configs and CI secrets.

## Git conventions

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Prefer small, focused commits

## UI shell

- **Layout:** Fixed top nav — brand link, **`v{{ appVersion }}`** from `web/src/app/version.ts` (`package.json` version), links **DIRECTORY** and **BENCHMARKS** only. No sidebar filter rails.
- **`/models`** is routed but **not** linked in the nav (placeholder page).

## Sitemap

| Path | Purpose |
|------|---------|
| `/` | Redirects to `/directory` |
| `/directory` | Comparison table + search |
| `/directory/:providerId` | Provider page (`ProviderComponent`) |
| `/directory/:providerId/:planId` | Same component; optional plan segment |
| `/benchmarks` | Placeholder |
| `/models` | Placeholder (not in main nav) |

**Example URL segments** (must match DB slugs):

- `/directory/alibaba-cloud-model-studio-coding-plan`
- `/directory/alibaba-cloud-model-studio-coding-plan/lite`

**Provider page** is still mostly **static/mock** in `provider.component.ts`; loading real provider/plan data from Supabase is follow-up work.
