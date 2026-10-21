-- Fidelity / integrity audit results, one row per (plan, model, test, run).
--
-- Written by `benchmarks/audit/ingest.py` after `benchmarks/audit/run_audit.py`
-- compares a plan endpoint's artifact against the official-API reference
-- artifact for the same model. The web app reads the latest row per
-- (plan_id, model_id, test_name) through `latest_audit_results`.
--
-- status:
--   pass          the target is statistically indistinguishable from the reference
--   fail          the gap exceeds the test's threshold AND survives the
--                 Benjamini–Hochberg correction across that audit's tests
--   inconclusive  too few usable samples / errors on either side
--   error         the run itself failed (auth, 429 storm, schema mismatch)

create table if not exists public.audit_results (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.plans (id) on delete cascade,
  model_id uuid not null references public.models (id) on delete cascade,
  run_at timestamptz not null default now(),
  test_name text not null,
  family text not null,
  status text not null check (status in ('pass', 'fail', 'inconclusive', 'error')),
  -- The headline statistic for this test (e.g. digit_accuracy, tool_call_valid_rate).
  metric text,
  reference_value double precision,
  target_value double precision,
  -- Raw and BH-adjusted p-values (null when the test has no p-value).
  p_value double precision,
  q_value double precision,
  summary text,
  reference_label text not null,
  target_label text not null,
  panel_id text,
  details jsonb not null default '{}'::jsonb
);

create index if not exists audit_results_plan_model_test_run_at_idx
  on public.audit_results (plan_id, model_id, test_name, run_at desc);

alter table public.audit_results enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'audit_results' and policyname = 'anon_read'
  ) then
    create policy anon_read on public.audit_results
      for select to anon, authenticated using (true);
  end if;
end $$;

create or replace view public.latest_audit_results
with (security_invoker = true) as
select distinct on (plan_id, model_id, test_name) *
from public.audit_results
order by plan_id, model_id, test_name, run_at desc;

-- Richer performance rows: one benchmark_runs row now summarizes a probe
-- session (several requests) rather than a single request.
alter table public.benchmark_runs add column if not exists samples integer;
alter table public.benchmark_runs add column if not exists error_rate double precision;
alter table public.benchmark_runs add column if not exists tps_p10 double precision;
alter table public.benchmark_runs add column if not exists ttft_p90_s double precision;

-- Where the plan is sold and what it officially promises; surfaced on plan pages.
alter table public.plans add column if not exists url text;
alter table public.plans add column if not exists advertised_limits text;
