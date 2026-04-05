# AI Coding Plan Comparison & Watchdog - Agent Guidelines

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
python benchmarks/benchmark_tps.py
python benchmarks/benchmark_heavy.py
```

## Project Structure

```
.
├── .github/workflows/
├── benchmarks/
├── web/              # Angular frontend
├── supabase/
└── requirements.txt
```

## Security

- Never commit API keys or secrets
- Use environment variables for sensitive data

## Git Conventions

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Keep commits atomic

## Sitemap

```
/                          # Landing / hero page
/directory                 # All providers, filterable (main comparison table)
/directory/[provider]      # Provider detail - their plans, models, meta
/directory/[provider]/[plan]  # Specific plan detail - models, pricing, benchmarks
/models                    # Model-centric view - all models, cross-provider
/models/[model]            # Model detail - which providers/plans offer it, scores
/benchmarks                # Benchmark explorer / leaderboard
```

**URL Examples:**
- `/directory/alibaba-model-studio` → Provider page
- `/directory/alibaba-model-studio/lite` → Plan detail page
- `/models/qwen-2.5` → Model page showing all plans with this model
