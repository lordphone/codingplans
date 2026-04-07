import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';
import type { DirectoryModelRow, DirectoryPlan, DirectoryProvider } from '../pages/directory/directory.models';
import type {
  ProviderPageData,
  ProviderPageModelRow,
  ProviderPagePlan,
  ProviderPageQuantColor
} from '../pages/provider/provider.models';
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

    const { statsByPlanModel, latestQuantByPlanModel } = await this.loadBenchmarkAggregatesForPlanIds(planIds);

    return mapProvidersToDirectory(providers, statsByPlanModel, latestQuantByPlanModel);
  }

  /**
   * One provider by `slug` (same as directory URL segment): nested plans → plan_models → models;
   * **7-day** TPS/TTFT averages and **latest** non-null quantization per plan+model (same rules as directory).
   */
  async fetchProviderPageFromSupabase(providerSlug: string): Promise<ProviderPageData | null> {
    const { data: raw, error } = await this.supabase
      .from('providers')
      .select(DIRECTORY_PROVIDER_SELECT)
      .eq('slug', providerSlug)
      .maybeSingle();

    if (error) {
      throw error;
    }
    if (!raw) {
      return null;
    }

    const provider = raw as ProviderWithPlansAndModels;
    const planIds = [...new Set((provider.plans ?? []).filter(pl => pl.is_active).map(pl => pl.id))];

    const { statsByPlanModel, latestQuantByPlanModel, latestRunAtIso } =
      await this.loadBenchmarkAggregatesForPlanIds(planIds);

    const plans = mapPlansForProviderPage(provider, statsByPlanModel, latestQuantByPlanModel);

    return {
      providerName: provider.name,
      lastUpdated: formatLastUpdatedUtc(latestRunAtIso, provider.created_at),
      plans
    };
  }

  private async loadBenchmarkAggregatesForPlanIds(planIds: string[]): Promise<{
    statsByPlanModel: Map<string, PlanModelBenchmarkStats>;
    latestQuantByPlanModel: Map<string, string>;
    latestRunAtIso: string | null;
  }> {
    const statsByPlanModel = new Map<string, PlanModelBenchmarkStats>();
    const latestQuantByPlanModel = new Map<string, string>();
    let latestRunAtIso: string | null = null;

    if (planIds.length === 0) {
      return { statsByPlanModel, latestQuantByPlanModel, latestRunAtIso };
    }

    const sinceIso = rollingWindowStartUtcIso(BENCHMARK_ROLLING_DAYS);

    const [perfRes, quantRes, latestRes] = await Promise.all([
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
        .order('run_at', { ascending: false }),
      this.supabase
        .from('benchmark_runs')
        .select('run_at')
        .in('plan_id', planIds)
        .order('run_at', { ascending: false })
        .limit(1)
        .maybeSingle()
    ]);

    if (perfRes.error) {
      throw perfRes.error;
    }
    if (quantRes.error) {
      throw quantRes.error;
    }
    if (latestRes.error) {
      throw latestRes.error;
    }

    buildSevenDayStatsIntoMap((perfRes.data ?? []) as BenchmarkRun[], statsByPlanModel);
    buildLatestQuantizationMap(quantRes.data ?? [], latestQuantByPlanModel);
    latestRunAtIso = latestRes.data?.run_at ?? null;

    return { statsByPlanModel, latestQuantByPlanModel, latestRunAtIso };
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
        quantizationStatus: inferQuantizationStatus(latestQ)
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

/** Low-bit integer weights (INT4/INT8, etc.) — flag like provider page “aggressive” tiers (red, not FP16-green). */
function inferQuantizationStatus(quantization: string): 'scam' | 'verified' {
  const q = quantization.toLowerCase();
  if (q.includes('scam') || /\breset\b/.test(q)) {
    return 'scam';
  }
  if (/\bint4\b|\bint8\b/.test(q) || q.includes('int8/4') || q.includes('int4/8')) {
    return 'scam';
  }
  return 'verified';
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

function mapPlansForProviderPage(
  provider: ProviderWithPlansAndModels,
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>,
  latestQuantByPlanModel: Map<string, string>
): ProviderPagePlan[] {
  return (provider.plans ?? [])
    .filter(pl => pl.is_active)
    .sort((a, b) => comparePlansByPriceThenName(a, b))
    .map(pl => mapOnePlanForProviderPage(pl, statsByPlanModel, latestQuantByPlanModel))
    .filter((p): p is ProviderPagePlan => p !== null);
}

function mapOnePlanForProviderPage(
  plan: ProviderWithPlansAndModels['plans'][number],
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>,
  latestQuantByPlanModel: Map<string, string>
): ProviderPagePlan | null {
  const junctions = [...(plan.plan_models ?? [])].sort((a, b) =>
    (a.models?.name ?? '').localeCompare(b.models?.name ?? '')
  );

  const models: ProviderPageModelRow[] = [];
  for (const pm of junctions) {
    const model = pm.models;
    if (!model?.slug) {
      continue;
    }
    const key = `${plan.id}:${pm.model_id}`;
    const stats = statsByPlanModel.get(key);
    const latestQ = latestQuantByPlanModel.get(key)?.trim();

    let quantizationColor: ProviderPageQuantColor;
    let quantization: string;
    if (!latestQ) {
      quantization = '—';
      quantizationColor = 'neutral';
    } else {
      quantization = latestQ.toUpperCase();
      quantizationColor = inferQuantizationStatus(latestQ) === 'scam' ? 'tertiary' : 'secondary';
    }

    models.push({
      id: model.slug,
      name: model.name,
      quantization,
      quantizationColor,
      tps: stats?.avgTps != null ? String(Math.round(stats.avgTps)) : '—',
      ttft: formatProviderTtft(stats?.avgTtftS ?? null)
    });
  }

  if (models.length === 0) {
    return null;
  }

  return {
    id: plan.slug,
    name: plan.name,
    tierId: plan.slug.replace(/-/g, ' ').toUpperCase(),
    price: formatMonthlyPrice(plan.price_per_month, plan.currency),
    period: '/ MO',
    models
  };
}

function formatLastUpdatedUtc(latestRunAt: string | null, fallbackCreatedAt: string): string {
  const iso = latestRunAt ?? fallbackCreatedAt;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return '—';
  }
  return `${d.toISOString().replace('T', ' ').slice(0, 19)} UTC`;
}

/** TTFT for provider cards: seconds → `0.75S`, sub-second → `NNN MS`. */
function formatProviderTtft(seconds: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) {
    return '—';
  }
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)} MS`;
  }
  return `${seconds.toFixed(2)}S`;
}

