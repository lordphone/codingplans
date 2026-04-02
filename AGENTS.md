# AI Coding Plan Comparison & Watchdog - Agent Guidelines

## Project Overview

A website comparing AI coding plans (Alibaba Cloud Model Studio, Minimax, Kimi, Z.ai) that monitors whether providers deliver promised performance. Core focus: detecting hidden throttling, undisclosed quantization, model swapping, and peak-hour degradation.

## Tech Stack

- **Frontend**: SvelteKit (SSR, routing, UI)
- **Backend**: FastAPI (Python) - business logic, benchmarks, scheduling
- **Database**: PostgreSQL
- **Job Scheduling**: APScheduler or Celery
- **Cache**: Redis

## Build Commands

### Frontend (SvelteKit)

```bash
# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run linting
npm run lint

# Run type checking
npm run check

# Run a single test
npm run test -- --run <test-file>

# Or with Playwright
npx playwright test <test-file>
```

### Backend (FastAPI)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Run single test
pytest tests/path/to/test_file.py::test_function_name

# Run with coverage
pytest --cov=app --cov-report=html

# Linting
ruff check .
ruff check --fix .

# Type checking
mypy app/

# Format code
ruff format .
```

### Docker (Full Stack)

```bash
# Build and run all services
docker-compose up --build

# Run only backend
docker-compose up backend

# Run tests in container
docker-compose exec backend pytest
```

## Code Style Guidelines

### Python (FastAPI)

#### Imports
- Standard library first, then third-party, then local
- Use absolute imports: `from app.models.user import User`
- Group: `import` then `from` imports
- Sort alphabetically within groups

```python
import asyncio
from datetime import datetime
from typing import Optional

import redis
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.models.provider import Provider
from app.services.benchmark import BenchmarkService
```

#### Formatting
- Line length: 100 characters max
- Use Black formatter (integrated via ruff)
- 4 spaces for indentation (no tabs)

#### Types
- Use type hints for all function signatures
- Prefer `Optional[X]` over `X | None`
- Use `from typing import` for complex types

```python
def calculate_tps(
    tokens: int,
    duration_seconds: float,
    provider_id: str,
) -> float:
    """Calculate tokens per second for a benchmark run."""
    if duration_seconds <= 0:
        raise ValueError("Duration must be positive")
    return tokens / duration_seconds
```

#### Naming Conventions
- Variables/functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`
- Database models: `PascalCase` with `Table` suffix option

#### Error Handling
- Use custom exception classes for domain errors
- Return proper HTTP status codes (404 for not found, 429 for rate limits)
- Log errors with appropriate level

```python
class ProviderNotFoundError(Exception):
    """Raised when a provider cannot be found."""
    pass

@app.get("/providers/{provider_id}")
async def get_provider(provider_id: str):
    provider = await provider_service.get(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider
```

#### Database (SQLAlchemy)
- Use async SQLAlchemy 2.0 style
- Define models in `app/models/`
- Use migrations with Alembic

```python
class BenchmarkResult(Base):
    __tablename__ = "benchmark_results"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(50))
    tps: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### TypeScript/Svelte (Frontend)

#### Imports
- Group: Svelte imports, then third-party, then local components/utils
- Absolute imports from `$lib/` for project code

```svelte
<script lang="ts">
  import { page } from '$app/stores';
  import type { BenchmarkResult } from '$lib/types';
  import ProviderCard from '$lib/components/ProviderCard.svelte';
</script>
```

#### Formatting
- Follow SvelteKit conventions
- Use ESLint + Prettier (or Svelte's built-in formatter)
- Max line length: 100

#### Types
- Define shared types in `$lib/types/`
- Use interfaces for objects, types for unions

```typescript
export interface BenchmarkResult {
  id: string;
  provider: string;
  tps: number;
  timestamp: Date;
  peakHours: boolean;
}

export type ProviderStatus = 'healthy' | 'throttled' | 'degraded' | 'down';
```

### Project Structure

```
.
├── app/                      # FastAPI backend
│   ├── api/                  # API routes
│   │   └── v1/
│   │       ├── providers.py
│   │       └── benchmarks.py
│   ├── core/                 # Config, security
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── services/             # Business logic
│   ├── tasks/                # Background jobs
│   └── main.py               # App entry point
├── src/                      # SvelteKit frontend
│   ├── lib/
│   │   ├── components/       # Svelte components
│   │   ├── server/           # Server-side code
│   │   ├── stores/           # Svelte stores
│   │   └── types/            # TypeScript types
│   └── routes/               # SvelteKit pages
├── tests/                    # Python tests
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── requirements.txt
└── package.json
```

## Watchdog-Specific Guidelines

### Benchmarking

- Store raw benchmark data, not just aggregated results
- Track timestamps for all measurements
- Record provider response headers (rate limits, model versions)
- Compare against advertised limits, not just historical data

### Model Fingerprinting

- Track response characteristics (token probabilities, timing patterns)
- Store model identifiers when available
- Detect quantization through latency patterns

### Performance Metrics to Track

- TPS under various load conditions
- Time to first token (TTFT)
- Peak vs off-peak performance
- Rate limit behavior vs advertised limits
- Output consistency (same prompt, different times)

## Database Conventions

- Use migrations for all schema changes
- Add indexes for frequently queried columns
- Soft delete where appropriate (use `deleted_at` timestamp)
- Track `created_at` and `updated_at` on all tables

## API Design

- RESTful endpoints with `/api/v1/` prefix
- Use proper HTTP verbs (GET, POST, PUT, DELETE)
- Return consistent JSON response format
- Version API in URL path

## Testing

- Write unit tests for services
- Write integration tests for API endpoints
- Mock external API calls in tests
- Test edge cases (empty results, errors, rate limits)
- Include benchmark accuracy tests

## Security

- Never commit API keys or secrets (use environment variables)
- Validate all input with Pydantic schemas
- Use dependency injection for services
- Implement proper CORS settings

## Git Conventions

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Keep commits atomic and focused
- Write meaningful commit messages