# AI Coding Plan Comparison & Watchdog - Agent Guidelines

## Project Overview

A website comparing AI coding plans (Alibaba Cloud Model Studio, Minimax, Kimi, Z.ai) that monitors whether providers deliver promised performance. Core focus: detecting hidden throttling, undisclosed quantization, model swapping, and peak-hour degradation.

## Tech Stack

- **Frontend**: Angular (SSR with Angular Universal, routing, UI)
- **Database**: Supabase (PostgreSQL)
- **Benchmarking (Lightweight)**: GitHub Actions - TPS benchmarks every 2-4 hours
- **Benchmarking (Heavy)**: Local machine - comprehensive tests weekly/ad-hoc

## Architecture

```
Angular ──► Supabase DB ◄── GitHub Actions (TPS, every 2-4h)
                      ▲
                      └── Local scripts (heavy benchmarks, manual)
```

### Why No Backend?

This architecture avoids needing a traditional backend server:
- **GitHub Actions** handles scheduled lightweight benchmarks
- **Supabase** provides database + optional Edge Functions if needed later
- **Local scripts** handle heavy benchmarks with no time limits
- **Completely free** hosting tier

FastAPI can be added later if needed for:
- Real-time API endpoints
- User-triggered benchmarks on-demand
- Public API for third-party access
- Webhooks from AI providers

## Build Commands

### Frontend (Angular)

```bash
# Install dependencies
npm install

# Development server
ng serve

# Build for production
ng build

# Build with SSR
ng build && ng run app:server

# Run linting
ng lint
```

### Benchmark Scripts (Python)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run TPS benchmark locally (for testing)
python scripts/benchmark_tps.py

# Run heavy benchmarks locally
python scripts/benchmark_heavy.py

# Linting
ruff check .
ruff check --fix .

# Type checking
mypy scripts/

# Format code
ruff format .
```

### GitHub Actions

```bash
# Manually trigger workflow
gh workflow run benchmark.yml

# View workflow runs
gh run list

# View specific run logs
gh run view <run-id>
```

## Code Style Guidelines

### Python (Benchmark Scripts)

#### Imports
- Standard library first, then third-party, then local
- Sort alphabetically within groups

```python
import asyncio
from datetime import datetime
from typing import Optional

from supabase import create_client
from pydantic import BaseModel

from config import settings
from models.benchmark import BenchmarkResult
```

#### Formatting
- Line length: 100 characters max
- 4 spaces for indentation (no tabs)
- Use ruff format (Black-compatible)

#### Types
- Use type hints for all function signatures
- Prefer `Optional[X]` over `X | None`

#### Naming Conventions
- Variables/functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

### Angular/TypeScript (Frontend)

#### Imports
- Group: Angular core, third-party, then local
- Use barrel exports (index.ts) where appropriate

```typescript
import { Component, OnInit, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';

import { ProviderService } from './services/provider.service';
import { BenchmarkResult } from './models/benchmark-result.model';
import { ProviderCardComponent } from './components/provider-card/provider-card.component';
```

#### Components
- Use standalone components (Angular 14+)
- One file per component when small, co-locate when logical
- Use OnPush change detection by default

```typescript
@Component({
  selector: 'app-provider-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './provider-card.component.html',
  styleUrls: ['./provider-card.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class ProviderCardComponent implements OnInit {
  @Input() provider!: Provider;
  @Output() selected = new EventEmitter<string>();
  
  isExpanded = signal(false);
}
```

#### Services
- Use providedIn: 'root' for singleton services
- Use signals for reactive state (Angular 16+)
- Use Supabase JS client for database operations

```typescript
@Injectable({ providedIn: 'root' })
export class BenchmarkService {
  private supabase = inject(SupabaseService).client;
  
  getResults(providerId: string): Observable<BenchmarkResult[]> {
    return from(
      this.supabase
        .from('benchmarks')
        .select('*')
        .eq('provider_id', providerId)
    ).pipe(map(response => response.data));
  }
}
```

#### Types/Interfaces
- Define models in `src/app/models/`
- Use interfaces for data structures

```typescript
export interface BenchmarkResult {
  id: string;
  provider: string;
  tps: number;
  timestamp: Date;
  source: 'github-actions' | 'local';
  peak_hours: boolean;
}

export type ProviderStatus = 'healthy' | 'throttled' | 'degraded' | 'down';
```

#### Naming Conventions
- Components: `PascalCase` (e.g., `ProviderListComponent`)
- Services: `PascalCase` with `Service` suffix
- Models: `PascalCase` with optional suffix (e.g., `Provider`, `ProviderModel`)
- Files: `kebab-case` (e.g., `provider-list.component.ts`)

#### Formatting
- Use ESLint with Angular-specific rules
- Prettier for code formatting
- Max line length: 100

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── benchmark.yml           # GitHub Actions workflow for TPS benchmarks
├── scripts/                         # Python benchmark scripts
│   ├── benchmark_tps.py            # Lightweight TPS benchmark
│   ├── benchmark_heavy.py          # Comprehensive benchmark suite
│   ├── providers/                   # Provider-specific implementations
│   │   ├── alibaba.py
│   │   ├── minimax.py
│   │   ├── kimi.py
│   │   └── zai.py
│   ├── models/                      # Pydantic models
│   ├── utils/                       # Shared utilities
│   └── config.py                    # Configuration
├── src/app/                         # Angular frontend
│   ├── core/                        # Singleton services, guards
│   ├── features/                    # Feature modules/components
│   ├── shared/                      # Shared components, pipes, directives
│   ├── models/                      # TypeScript interfaces
│   ├── services/                    # Data services (Supabase client)
│   └── app.component.ts             # Root component
├── supabase/
│   └── migrations/                   # Database schema migrations
├── tests/                           # Python tests for benchmark scripts
├── requirements.txt                 # Python dependencies
├── package.json                     # Node dependencies
└── angular.json
```

## Watchdog-Specific Guidelines

### Benchmarking Strategy

#### GitHub Actions (Lightweight - TPS)
- **Frequency**: Every 2-4 hours
- **Duration**: ~5 minutes max
- **Metrics**: TPS, TTFT, basic latency
- **Purpose**: Continuous monitoring, catch peak-hour degradation

#### Local Scripts (Heavy - Comprehensive)
- **Frequency**: Weekly or ad-hoc
- **Duration**: Unlimited
- **Metrics**: Full evaluation suites, complex prompts, quality assessment
- **Purpose**: Deep analysis, model comparison, quality verification

### Data Tracking
- Store raw benchmark data, not just aggregated results
- Track timestamps for all measurements
- Include `source` field: `'github-actions'` or `'local'`
- Compare against advertised limits, not just historical data

### Performance Metrics to Track
- TPS under various load conditions
- Time to first token (TTFT)
- Peak vs off-peak performance
- Rate limit behavior vs advertised limits
- Model quality degradation over time

## Security

- Never commit API keys or secrets (use environment variables)
- Store secrets in GitHub repository secrets for Actions
- Use Supabase Row Level Security (RLS) for data protection
- Use Angular's built-in XSS protection
- Validate all input before storing in database

## Git Conventions

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Keep commits atomic and focused