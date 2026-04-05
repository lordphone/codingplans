# AI Coding Plan Comparison - Agent Guidelines

## Project Overview

A website comparing AI coding plans that monitors whether providers deliver promised performance.

## Tech Stack

- **Frontend**: Angular + Tailwind CSS
- **Database**: Supabase (PostgreSQL)
- **Benchmarking**: GitHub Actions (lightweight) + Local scripts (heavy)

## Architecture

```
Angular ──► Supabase DB ◄── GitHub Actions (TPS benchmarks)
                      ▲
                      └── Local scripts (heavy benchmarks)
```

## Build Commands

### Frontend (Angular)

```bash
cd web
npm install
ng serve          # Development server
ng build          # Production build
```

### Python Scripts

```bash
python benchmarks/performance/benchmark_tps.py --config benchmarks/providers.json
```

## Project Structure

```
.
├── .github/workflows/
├── benchmarks/
│   ├── performance/       # TPS, TTFT benchmarks (realistic coding scenarios)
│   ├── quantize/          # Model quality / quantization testing
│   ├── providers.json     # Shared provider config (gitignored)
│   └── providers.example.json
├── web/                   # Angular frontend
│   └── src/
│       └── app/
│           ├── services/  # API services (Supabase)
│           ├── types/     # TypeScript interfaces
│           └── pages/
├── supabase/
└── requirements.txt
```

## Database (Supabase)

**Source of truth:** the live Postgres schema in Supabase (SQL Editor / migrations). Do not treat the frontend types file as authoritative if it drifts.

**Core tables:** `providers` → `plans` (`provider_id`); `models`; `plan_models` (`plan_id`, `model_id`) for many-to-many; `benchmark_runs` for time-series metrics per plan+model (wide columns: e.g. `tps`, `ttft_s`, nullable `quantization`).

**App reads:** nested `.select()` from `providers` through `plans` → `plan_models` → `models` (requires FKs). Load `benchmark_runs` in a second query (or later a view) and merge in the app for latest metrics.

**RLS:** `anon` = read-only `SELECT` on public directory data; benchmark scripts and dashboard use **service role** for writes.

**Types:** `web/src/app/types/database.types.ts` should match tables; prefer `supabase gen types typescript` when using the CLI.

## Security

- Never commit API keys or secrets
- Use environment variables for sensitive data

## Git Conventions

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Keep commits atomic

## Sitemap

```
/                          # Redirects to /directory
/directory                 # All providers, filterable (main comparison table)
/directory/:providerId     # Provider detail - their plans, models, meta
/directory/:providerId/:planId  # Specific plan detail - models, pricing, benchmarks
/models                    # Model-centric view - placeholder
/benchmarks                # Benchmark explorer / placeholder
```

**URL Examples:**
- `/directory/alibaba-model-studio` → Provider page
- `/directory/alibaba-model-studio/lite` → Plan detail page

**Note:** Provider detail handles both :providerId and :planId routes. Models and benchmarks pages are placeholders.
