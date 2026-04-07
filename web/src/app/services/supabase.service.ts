import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';
import type { DirectoryModelRow, DirectoryPlan, DirectoryProvider } from '../pages/directory/directory.models';
import type {
  PlanPerformanceDayPoint,
  PlanPerformanceModelBlock,
  PlanPerformancePage,
  PlanQuantRunRow
} from '../pages/plan/plan.models';
import type { BenchmarkRun, ProviderWithPlansAndModels } from '../types/database.types';

const DIRECTORY_PROVIDER_SELECT = `
  id,
  name,
  slug,
  description,
  website_url,
  logo_url,
  created_at,
  plans (
    id,
    provider_id,
    name,
    slug,
    description,
    price_per_month,
    currency,
    is_active,
    plan_models (
      plan_id,
      model_id,
      models (
        id,
        name,
        slug,
        description
      )
    )
  )
`;

@Injectable({
  providedIn: 'root'
})
export class SupabaseService {
  private supabase: SupabaseClient;

  constructor() {
    this.supabase = createClient(environment.supabaseUrl, environment.supabaseKey);
  }

  /**
   * Directory listing: nested providers → plans → plan_models → models; **7-day averages** for TPS/TTFT;
   * **quantization** from the **latest** run (any time) with non-null `quantization` for that plan+model.
   * **Usage limits** column shows '—' until we surface `plan_models.usage_limit` again.
   */
  async fetchDirectoryFromSupabase(): Promise<DirectoryProvider[]> {
    const { data: raw, error: providersError } = await this.supabase
      .from('providers')
      .select(DIRECTORY_PROVIDER_SELECT)
      .order('name', { ascending: true });

    if (providersError) {
      throw providersError;
    }

    const providers = (raw ?? []) as unknown as ProviderWithPlansAndModels[];
    const planIds = [
      ...new Set(providers.flatMap(p => (p.plans ?? []).filter(pl => pl.is_active).map(pl => pl.id)))
    ];

    const statsByPlanModel = new Map<string, PlanModelBenchmarkStats>();
    const latestQuantByPlanModel = new Map<string, string>();

    if (planIds.length > 0) {
      const sinceIso = rollingWindowStartUtcIso(BENCHMARK_ROLLING_DAYS);

      const [perfRes, quantRes] = await Promise.all([
        this.supabase
          .from('benchmark_runs')
          .select('plan_id, model_id, tps, ttft_s, run_at')
          .in('plan_id', planIds)
          .gte('run_at', sinceIso),
        this.supabase
          .from('benchmark_runs')
          .select('plan_id, model_id, quantization, run_at')
          .in('plan_id', planIds)
          .not('quantization', 'is', null)
          .order('run_at', { ascending: false })
      ]);

      if (perfRes.error) {
        throw perfRes.error;
      }
      if (quantRes.error) {
        throw quantRes.error;
      }

      buildSevenDayStatsIntoMap((perfRes.data ?? []) as BenchmarkRun[], statsByPlanModel);
      buildLatestQuantizationMap(quantRes.data ?? [], latestQuantByPlanModel);
    }

    return mapProvidersToDirectory(providers, statsByPlanModel, latestQuantByPlanModel);
  }

  /**
   * Plan page: one plan (by provider + plan slug), models on that plan, and benchmark runs from the last
   * {@link PLAN_PAGE_BENCHMARK_DAYS} days (daily buckets for TPS / TTFT; quantization rows are individual runs).
   */
  async fetchPlanPerformancePage(providerSlug: string, planSlug: string): Promise<PlanPerformancePage | null> {
    const { data: provider, error: providerError } = await this.supabase
      .from('providers')
      .select('id, name, slug')
      .eq('slug', providerSlug)
      .maybeSingle();

    if (providerError) {
      throw providerError;
    }
    if (!provider) {
      return null;
    }

    const { data: planRaw, error: planError } = await this.supabase
      .from('plans')
      .select(
        `id, name, slug, description, price_per_month, currency, is_active,
         plan_models ( model_id, models ( id, name, slug ) )`
      )
      .eq('provider_id', provider.id)
      .eq('slug', planSlug)
      .maybeSingle();

    if (planError) {
      throw planError;
    }

    const planRow = planRaw as PlanWithModelsEmbed | null;
    if (!planRow || !planRow.is_active) {
      return null;
    }

    const junctions = [...(planRow.plan_models ?? [])]
      .filter((pm): pm is PlanModelJunction => Boolean(pm.models?.slug))
      .sort((a, b) => (a.models.name ?? '').localeCompare(b.models.name ?? ''));

    const baseMeta = {
      providerName: provider.name,
      providerSlug: provider.slug,
      planName: planRow.name,
      planSlug: planRow.slug,
      planSubtitle: planRow.description?.trim() ?? '',
      priceLabel: formatMonthlyPrice(planRow.price_per_month, planRow.currency),
      periodLabel: '/ month'
    };

    if (junctions.length === 0) {
      return { ...baseMeta, models: [] };
    }

    const sinceIso = rollingWindowStartUtcIso(PLAN_PAGE_BENCHMARK_DAYS);
    const { data: runRows, error: runsError } = await this.supabase
      .from('benchmark_runs')
      .select('plan_id, model_id, tps, ttft_s, quantization, run_at')
      .eq('plan_id', planRow.id)
      .gte('run_at', sinceIso)
      .order('run_at', { ascending: true });

    if (runsError) {
      throw runsError;
    }

    const runs = (runRows ?? []) as BenchmarkRun[];
    const dayMeta = lastNDayKeysUtc(PLAN_PAGE_BENCHMARK_DAYS);

    const models: PlanPerformanceModelBlock[] = junctions.map(pm => {
      const series = buildDaySeriesForModel(pm.model_id, runs, dayMeta);
      const quantRuns = buildQuantRunsForModel(pm.model_id, runs);
      return {
        modelId: pm.model_id,
        modelName: pm.models.name,
        modelSlug: pm.models.slug,
        tpsSeries: series,
        ttftSeries: series,
        quantRuns
      };
    });

    return { ...baseMeta, models };
  }

  async getData(table: string) {
    const { data, error } = await this.supabase.from(table).select('*');
    if (error) throw error;
    return data;
  }

  async getById(table: string, id: string) {
    const { data, error } = await this.supabase.from(table).select('*').eq('id', id).single();
    if (error) throw error;
    return data;
  }
}

/** How far back to include runs when computing directory performance averages (Option A: aggregate in app). */
const BENCHMARK_ROLLING_DAYS = 7;

/** Plan page charts: UTC daily buckets over this many days. */
const PLAN_PAGE_BENCHMARK_DAYS = 30;

interface PlanModelJunction {
  model_id: string;
  models: { id: string; name: string; slug: string };
}

interface PlanWithModelsEmbed {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  price_per_month: number | null;
  currency: string;
  is_active: boolean;
  plan_models: PlanModelJunction[] | null;
}

/** Rolling-window averages for one (plan_id, model_id); quantization is loaded separately. */
interface PlanModelBenchmarkStats {
  avgTps: number | null;
  avgTtftS: number | null;
}

function rollingWindowStartUtcIso(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString();
}

function buildSevenDayStatsIntoMap(rows: BenchmarkRun[], target: Map<string, PlanModelBenchmarkStats>): void {
  type Acc = { tpsValues: number[]; ttftValues: number[] };

  const accByKey = new Map<string, Acc>();
  for (const r of rows) {
    const key = `${r.plan_id}:${r.model_id}`;
    let acc = accByKey.get(key);
    if (!acc) {
      acc = { tpsValues: [], ttftValues: [] };
      accByKey.set(key, acc);
    }

    if (r.tps != null && !Number.isNaN(Number(r.tps))) {
      acc.tpsValues.push(Number(r.tps));
    }
    if (r.ttft_s != null && !Number.isNaN(Number(r.ttft_s))) {
      acc.ttftValues.push(Number(r.ttft_s));
    }
  }

  for (const [key, acc] of accByKey) {
    const avgTps =
      acc.tpsValues.length > 0 ? acc.tpsValues.reduce((s, x) => s + x, 0) / acc.tpsValues.length : null;
    const avgTtftS =
      acc.ttftValues.length > 0
        ? acc.ttftValues.reduce((s, x) => s + x, 0) / acc.ttftValues.length
        : null;

    target.set(key, { avgTps, avgTtftS });
  }
}

/** Latest non-empty `quantization` per (plan_id, model_id); `rows` should be ordered by `run_at` descending. */
function buildLatestQuantizationMap(
  rows: Array<Pick<BenchmarkRun, 'plan_id' | 'model_id' | 'quantization' | 'run_at'>>,
  target: Map<string, string>
): void {
  for (const r of rows) {
    const q = typeof r.quantization === 'string' ? r.quantization.trim() : '';
    if (!q) {
      continue;
    }
    const key = `${r.plan_id}:${r.model_id}`;
    if (!target.has(key)) {
      target.set(key, q);
    }
  }
}

function mapProvidersToDirectory(
  providers: ProviderWithPlansAndModels[],
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>,
  latestQuantByPlanModel: Map<string, string>
): DirectoryProvider[] {
  return providers
    .map(p => mapOneProvider(p, statsByPlanModel, latestQuantByPlanModel))
    .filter(dp => dp.plans.length > 0);
}

function mapOneProvider(
  provider: ProviderWithPlansAndModels,
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>,
  latestQuantByPlanModel: Map<string, string>
): DirectoryProvider {
  const plans = (provider.plans ?? [])
    .filter(pl => pl.is_active)
    .sort((a, b) => comparePlansByPriceThenName(a, b))
    .map(pl => mapOnePlan(pl, statsByPlanModel, latestQuantByPlanModel))
    .filter((pl): pl is DirectoryPlan => pl !== null);

  return {
    id: provider.slug,
    name: provider.name,
    plans
  };
}

/** Directory UX: cheapest plan first; missing/null price sorts last. */
function comparePlansByPriceThenName(
  a: ProviderWithPlansAndModels['plans'][number],
  b: ProviderWithPlansAndModels['plans'][number]
): number {
  const pa = a.price_per_month;
  const pb = b.price_per_month;
  const na = pa != null && !Number.isNaN(pa) ? pa : Number.POSITIVE_INFINITY;
  const nb = pb != null && !Number.isNaN(pb) ? pb : Number.POSITIVE_INFINITY;
  if (na !== nb) {
    return na - nb;
  }
  return a.name.localeCompare(b.name);
}

function mapOnePlan(
  plan: ProviderWithPlansAndModels['plans'][number],
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>,
  latestQuantByPlanModel: Map<string, string>
): DirectoryPlan | null {
  const junctions = [...(plan.plan_models ?? [])].sort((a, b) => {
    const na = a.models?.name ?? '';
    const nb = b.models?.name ?? '';
    return na.localeCompare(nb);
  });

  const modelRows: DirectoryModelRow[] = [];
  for (const pm of junctions) {
    const model = pm.models;
    if (!model?.slug) {
      continue;
    }
    const key = `${plan.id}:${pm.model_id}`;
    const stats = statsByPlanModel.get(key);
    const latestQ = latestQuantByPlanModel.get(key)?.trim();

    const modelRowBase = {
      rowId: `${plan.slug}:${model.slug}`,
      modelSlug: model.slug,
      modelName: model.name,
      usageLabel: USAGE_PLACEHOLDER,
      tps: stats?.avgTps != null ? Math.round(stats.avgTps) : 0,
      ttftS: stats?.avgTtftS ?? null
    };

    if (!latestQ) {
      modelRows.push({
        ...modelRowBase,
        quantization: 'untested',
        quantizationStatus: 'untested' as const
      });
    } else {
      modelRows.push({
        ...modelRowBase,
        quantization: latestQ,
        quantizationStatus: inferQuantizationStatusFromLabel(latestQ)
      });
    }
  }

  if (modelRows.length === 0) {
    return null;
  }

  return {
    id: plan.slug,
    name: plan.name,
    subtitle: plan.description?.trim() ?? '',
    price: formatMonthlyPrice(plan.price_per_month, plan.currency),
    period: '/ Month',
    modelRows
  };
}

const USAGE_PLACEHOLDER = '—';

/**
 * Low-bit integer weights (INT4/INT8, etc.) — flag like provider-detail “aggressive” tiers (red, not FP16-green).
 * Shared with plan page quantization timeline.
 */
export function inferQuantizationStatusFromLabel(quantization: string): 'scam' | 'verified' {
  const q = quantization.toLowerCase();
  if (q.includes('scam') || /\breset\b/.test(q)) {
    return 'scam';
  }
  if (/\bint4\b|\bint8\b/.test(q) || q.includes('int8/4') || q.includes('int4/8')) {
    return 'scam';
  }
  return 'verified';
}

function utcDayKeyFromIso(iso: string): string {
  const d = new Date(iso);
  const y = d.getUTCFullYear();
  const mo = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${mo}-${day}`;
}

function lastNDayKeysUtc(n: number): { key: string; label: string }[] {
  const out: { key: string; label: string }[] = [];
  for (let back = n - 1; back >= 0; back--) {
    const d = new Date();
    d.setUTCHours(0, 0, 0, 0);
    d.setUTCDate(d.getUTCDate() - back);
    const key = utcDayKeyFromIso(d.toISOString());
    const label = `${d.getUTCMonth() + 1}/${String(d.getUTCDate()).padStart(2, '0')}`;
    out.push({ key, label });
  }
  return out;
}

function buildDaySeriesForModel(
  modelId: string,
  runs: BenchmarkRun[],
  dayMeta: { key: string; label: string }[]
): PlanPerformanceDayPoint[] {
  const byDay = new Map<string, { tps: number[]; ttft: number[] }>();
  for (const { key } of dayMeta) {
    byDay.set(key, { tps: [], ttft: [] });
  }
  for (const r of runs) {
    if (r.model_id !== modelId) {
      continue;
    }
    const dk = utcDayKeyFromIso(r.run_at);
    const bucket = byDay.get(dk);
    if (!bucket) {
      continue;
    }
    if (r.tps != null && !Number.isNaN(Number(r.tps))) {
      bucket.tps.push(Number(r.tps));
    }
    if (r.ttft_s != null && !Number.isNaN(Number(r.ttft_s))) {
      bucket.ttft.push(Number(r.ttft_s));
    }
  }
  return dayMeta.map(({ key, label }) => {
    const b = byDay.get(key)!;
    const avgTps = b.tps.length > 0 ? b.tps.reduce((s, x) => s + x, 0) / b.tps.length : null;
    const avgTtftS = b.ttft.length > 0 ? b.ttft.reduce((s, x) => s + x, 0) / b.ttft.length : null;
    return { dayKey: key, label, avgTps, avgTtftS };
  });
}

function buildQuantRunsForModel(modelId: string, runs: BenchmarkRun[]): PlanQuantRunRow[] {
  const rows: PlanQuantRunRow[] = [];
  for (const r of runs) {
    if (r.model_id !== modelId) {
      continue;
    }
    const q = typeof r.quantization === 'string' ? r.quantization.trim() : '';
    if (!q) {
      continue;
    }
    const { dayLabel, timeLabel } = formatRunDayTimeUtc(r.run_at);
    rows.push({
      runAtIso: r.run_at,
      dayLabel,
      timeLabel,
      label: q,
      status: inferQuantizationStatusFromLabel(q)
    });
  }
  rows.sort((a, b) => b.runAtIso.localeCompare(a.runAtIso));
  return rows;
}

function formatRunDayTimeUtc(iso: string): { dayLabel: string; timeLabel: string } {
  const d = new Date(iso);
  const dayLabel = `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
  const timeLabel = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`;
  return { dayLabel, timeLabel };
}

function formatMonthlyPrice(amount: number | null, currency: string): string {
  if (amount == null || Number.isNaN(amount)) {
    return '—';
  }
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'USD'
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

