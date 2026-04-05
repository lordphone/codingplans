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
python benchmarks/benchmark_tps.py
python benchmarks/benchmark_heavy.py
```

## Project Structure

```
.
├── .github/workflows/
├── benchmarks/
├── web/                   # Angular frontend
│   └── src/
│       └── app/
│           ├── services/  # API services (Supabase)
│           ├── types/     # TypeScript interfaces
│           └── pages/
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
