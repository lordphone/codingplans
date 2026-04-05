# AI Coding Plan Comparison & Watchdog - Agent Guidelines

## Project Overview

A website comparing AI coding plans that monitors whether providers deliver promised performance.

## Tech Stack

- **Frontend**: Angular
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
