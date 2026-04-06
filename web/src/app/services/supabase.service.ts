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
   * Directory listing: nested providers → plans → plan_models → models, plus latest benchmark per (plan_id, model_id).
   * Usage limits are not in schema yet (`usageLabel` is '—').
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

    const runByPlanModel = new Map<string, BenchmarkRun>();
    if (planIds.length > 0) {
      const { data: runsRaw, error: benchError } = await this.supabase
        .from('benchmark_runs')
        .select('plan_id, model_id, tps, ttft_s, quantization, run_at')
        .in('plan_id', planIds)
        .order('run_at', { ascending: false });

      if (benchError) {
        throw benchError;
      }

      for (const row of runsRaw ?? []) {
        const r = row as BenchmarkRun;
        const key = `${r.plan_id}:${r.model_id}`;
        if (!runByPlanModel.has(key)) {
          runByPlanModel.set(key, r);
        }
      }
    }

    return mapProvidersToDirectory(providers, runByPlanModel);
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

function mapProvidersToDirectory(
  providers: ProviderWithPlansAndModels[],
  runByPlanModel: Map<string, BenchmarkRun>
): DirectoryProvider[] {
  return providers
    .map(p => mapOneProvider(p, runByPlanModel))
    .filter(dp => dp.plans.length > 0);
}

function mapOneProvider(
  provider: ProviderWithPlansAndModels,
  runByPlanModel: Map<string, BenchmarkRun>
): DirectoryProvider {
  const plans = (provider.plans ?? [])
    .filter(pl => pl.is_active)
    .sort((a, b) => comparePlansByPriceThenName(a, b))
    .map(pl => mapOnePlan(pl, runByPlanModel))
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
  runByPlanModel: Map<string, BenchmarkRun>
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
    const run = runByPlanModel.get(`${plan.id}:${pm.model_id}`);
    const quantText = run?.quantization?.trim() || '—';

    modelRows.push({
      rowId: `${plan.slug}:${model.slug}`,
      modelName: model.name,
      usageLabel: USAGE_PLACEHOLDER,
      tps: run?.tps ?? 0,
      ttftS: run?.ttft_s ?? null,
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
