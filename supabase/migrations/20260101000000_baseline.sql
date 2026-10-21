-- Baseline schema for the directory + benchmark time series.
--
-- The original tables were created by hand in the Supabase dashboard and never
-- captured as a migration. This file reconstructs them (from the old web
-- app's `database.types.ts`) so a fresh project can be provisioned from the
-- repo alone. Every statement is idempotent: on a project that already has
-- these tables it is a no-op.
--
-- Timestamped before 20260430000000_aggressively_quantized.sql so ordering is
-- correct on a fresh project. On the legacy linked project (which already has
-- the later migration recorded) push with `supabase db push --include-all`.

create extension if not exists pgcrypto;

create table if not exists public.providers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  description text,
  website_url text,
  logo_url text,
  created_at timestamptz not null default now()
);

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid not null references public.providers (id) on delete cascade,
  name text not null,
  slug text not null,
  description text,
  price_per_month numeric,
  currency text not null default 'USD',
  is_active boolean not null default true,
  unique (provider_id, slug)
);

create table if not exists public.models (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  description text
);

create table if not exists public.plan_models (
  plan_id uuid not null references public.plans (id) on delete cascade,
  model_id uuid not null references public.models (id) on delete cascade,
  usage_limit text,
  primary key (plan_id, model_id)
);

create table if not exists public.benchmark_runs (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.plans (id) on delete cascade,
  model_id uuid not null references public.models (id) on delete cascade,
  run_at timestamptz not null default now(),
  tps double precision,
  ttft_s double precision
);

create index if not exists benchmark_runs_plan_model_run_at_idx
  on public.benchmark_runs (plan_id, model_id, run_at desc);

-- Public read-only directory. Writes go through the service role (bypasses RLS).
alter table public.providers enable row level security;
alter table public.plans enable row level security;
alter table public.models enable row level security;
alter table public.plan_models enable row level security;
alter table public.benchmark_runs enable row level security;

do $$
declare t text;
begin
  foreach t in array array['providers', 'plans', 'models', 'plan_models', 'benchmark_runs'] loop
    if not exists (
      select 1 from pg_policies
      where schemaname = 'public' and tablename = t and policyname = 'anon_read'
    ) then
      execute format(
        'create policy anon_read on public.%I for select to anon, authenticated using (true)', t
      );
    end if;
  end loop;
end $$;
