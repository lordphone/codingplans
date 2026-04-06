import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';
import type { DirectoryModelRow, DirectoryPlan, DirectoryProvider } from '../pages/directory/directory.models';
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
   * Directory listing: nested providers → plans → plan_models → models, plus **rolling 7-day averages**
   * of TPS and TTFT per (plan_id, model_id) from `benchmark_runs`. Quantization label is taken from the
   * **most recent** run in that window (non-null only). Usage limits are not in schema yet (`usageLabel` is '—').
   */
  async fetchDirectoryFromSupabase(): Promise<DirectoryProvider[]> {
    const { data: raw, error: providersError } = await this.supabase
      .from('providers')
      .select(DIRECTORY_PROVIDER_SELECT)
      .order('name', { ascending: true });

    if (providersError) {
      throw providersError;
    }

    const providers = (raw ?? []) as ProviderWithPlansAndModels[];
    const planIds = [
      ...new Set(providers.flatMap(p => (p.plans ?? []).filter(pl => pl.is_active).map(pl => pl.id)))
    ];

    const statsByPlanModel = new Map<string, PlanModelBenchmarkStats>();
    if (planIds.length > 0) {
      const sinceIso = rollingWindowStartUtcIso(BENCHMARK_ROLLING_DAYS);
      const { data: runsRaw, error: benchError } = await this.supabase
        .from('benchmark_runs')
        .select('plan_id, model_id, tps, ttft_s, quantization, run_at')
        .in('plan_id', planIds)
        .gte('run_at', sinceIso);

      if (benchError) {
        throw benchError;
      }

      const runs = (runsRaw ?? []) as BenchmarkRun[];
      buildSevenDayStatsIntoMap(runs, statsByPlanModel);
    }

    return mapProvidersToDirectory(providers, statsByPlanModel);
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

/** Averages + latest-quantization metadata for one (plan_id, model_id) in the window. */
interface PlanModelBenchmarkStats {
  avgTps: number | null;
  avgTtftS: number | null;
  /** From the newest run in the window that had non-null `quantization`. */
  quantization: string | null;
}

function rollingWindowStartUtcIso(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString();
}

function buildSevenDayStatsIntoMap(rows: BenchmarkRun[], target: Map<string, PlanModelBenchmarkStats>): void {
  type Acc = {
    tpsValues: number[];
    ttftValues: number[];
    latestQ: { text: string; at: string } | null;
  };

  const accByKey = new Map<string, Acc>();
  for (const r of rows) {
    const key = `${r.plan_id}:${r.model_id}`;
    let acc = accByKey.get(key);
    if (!acc) {
      acc = { tpsValues: [], ttftValues: [], latestQ: null };
      accByKey.set(key, acc);
    }

    if (r.tps != null && !Number.isNaN(Number(r.tps))) {
      acc.tpsValues.push(Number(r.tps));
    }
    if (r.ttft_s != null && !Number.isNaN(Number(r.ttft_s))) {
      acc.ttftValues.push(Number(r.ttft_s));
    }

    const q = r.quantization?.trim();
    if (q) {
      if (!acc.latestQ || r.run_at > acc.latestQ.at) {
        acc.latestQ = { text: q, at: r.run_at };
      }
    }
  }

  for (const [key, acc] of accByKey) {
    const avgTps =
      acc.tpsValues.length > 0 ? acc.tpsValues.reduce((s, x) => s + x, 0) / acc.tpsValues.length : null;
    const avgTtftS =
      acc.ttftValues.length > 0
        ? acc.ttftValues.reduce((s, x) => s + x, 0) / acc.ttftValues.length
        : null;

    target.set(key, {
      avgTps,
      avgTtftS,
      quantization: acc.latestQ?.text ?? null
    });
  }
}

function mapProvidersToDirectory(
  providers: ProviderWithPlansAndModels[],
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>
): DirectoryProvider[] {
  return providers
    .map(p => mapOneProvider(p, statsByPlanModel))
    .filter(dp => dp.plans.length > 0);
}

function mapOneProvider(
  provider: ProviderWithPlansAndModels,
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>
): DirectoryProvider {
  const plans = (provider.plans ?? [])
    .filter(pl => pl.is_active)
    .sort((a, b) => comparePlansByPriceThenName(a, b))
    .map(pl => mapOnePlan(pl, statsByPlanModel))
    .filter((pl): pl is DirectoryPlan => pl !== null);

  return {
    id: provider.slug,
    name: provider.name,
    providerId: abbreviateUuid(provider.id),
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
  statsByPlanModel: Map<string, PlanModelBenchmarkStats>
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
    const stats = statsByPlanModel.get(`${plan.id}:${pm.model_id}`);
    const quantText = stats?.quantization?.trim() || '—';

    modelRows.push({
      rowId: `${plan.slug}:${model.slug}`,
      modelName: model.name,
      usageLabel: USAGE_PLACEHOLDER,
      tps: stats?.avgTps != null ? Math.round(stats.avgTps) : 0,
      ttftS: stats?.avgTtftS ?? null,
      quantization: quantText,
      quantizationStatus: inferQuantizationStatus(quantText)
    });
  }

  if (modelRows.length === 0) {
    return null;
  }

  return {
    id: plan.slug,
    name: plan.name,
    subtitle: plan.description?.trim() || '—',
    price: formatMonthlyPrice(plan.price_per_month, plan.currency),
    period: '/ Month',
    modelRows
  };
}

const USAGE_PLACEHOLDER = '—';

function inferQuantizationStatus(quantization: string): 'scam' | 'verified' {
  return quantization.toLowerCase().includes('scam') ? 'scam' : 'verified';
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

function abbreviateUuid(uuid: string): string {
  return uuid.replace(/-/g, '').slice(0, 8).toUpperCase();
}
