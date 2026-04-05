import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';
import type {
  BenchmarkRunRow,
  DisplayPlan,
  DisplayProvider,
  PlanDetailView,
  PlanWithRelations,
  ProviderWithPlans
} from '../types/database.types';

const PROVIDER_SELECT = `
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
      model_id,
      models ( id, name, slug, description )
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
   * Nested providers → plans → plan_models → models (requires FKs in Supabase).
   */
  async getProvidersWithPlans(): Promise<ProviderWithPlans[]> {
    const { data, error } = await this.supabase
      .from('providers')
      .select(PROVIDER_SELECT)
      .order('name');
    if (error) throw error;
    return (data ?? []) as unknown as ProviderWithPlans[];
  }

  /**
   * Single provider (by slug) with the same nested shape as the directory query.
   */
  async getProviderBySlug(slug: string): Promise<ProviderWithPlans | null> {
    const { data, error } = await this.supabase
      .from('providers')
      .select(PROVIDER_SELECT)
      .eq('slug', slug)
      .maybeSingle();
    if (error) throw error;
    return (data ?? null) as unknown as ProviderWithPlans | null;
  }

  /**
   * All benchmark runs (newest first); caller picks latest per plan+model.
   */
  async getBenchmarkRunsOrdered(): Promise<BenchmarkRunRow[]> {
    const { data, error } = await this.supabase
      .from('benchmark_runs')
      .select('id, plan_id, model_id, tps, ttft_s, quantization, recorded_at')
      .order('recorded_at', { ascending: false });
    if (error) throw error;
    return (data ?? []) as BenchmarkRunRow[];
  }

  /** Returns empty array if the table is missing or RLS denies access. */
  async getBenchmarkRunsOrderedSafe(): Promise<BenchmarkRunRow[]> {
    try {
      return await this.getBenchmarkRunsOrdered();
    } catch {
      return [];
    }
  }

  plansToDetailViews(plans: PlanWithRelations[], benchMap: Map<string, BenchmarkRunRow>): PlanDetailView[] {
    const active = plans.filter(pl => pl.is_active !== false);
    return active.map((plan, index) => {
      const joins = plan.plan_models ?? [];
      const modelNames = joins
        .map(j => j.models?.name)
        .filter((n): n is string => !!n);
      const modelTarget = modelNames.length ? modelNames.join(' / ') : '—';

      let bestTps = 0;
      let bestQ: string | null = null;
      for (const j of joins) {
        const key = `${plan.id}\0${j.model_id}`;
        const run = benchMap.get(key);
        if (run?.tps != null && run.tps > bestTps) {
          bestTps = run.tps;
          bestQ = run.quantization;
        }
      }

      const qDisp = this.quantizationDisplay(bestQ);
      const notice =
        plan.description?.trim() ||
        'No provider description on file. Metrics reflect the latest benchmark run per linked model.';

      return {
        id: plan.slug,
        name: plan.name.toUpperCase(),
        tierId: plan.slug.toUpperCase(),
        price: this.formatPrice(plan),
        period: '/ MO',
        modelTarget: modelTarget.toUpperCase(),
        quantization: qDisp.label,
        quantizationColor: qDisp.status === 'scam' ? 'tertiary' : 'secondary',
        tps: bestTps > 0 ? String(Math.round(bestTps * 10) / 10) : '—',
        notice: notice.toUpperCase(),
        isPro: index % 2 === 1
      };
    });
  }

  latestBenchmarkByPlanModel(runs: BenchmarkRunRow[]): Map<string, BenchmarkRunRow> {
    const map = new Map<string, BenchmarkRunRow>();
    for (const row of runs) {
      const key = `${row.plan_id}\0${row.model_id}`;
      if (!map.has(key)) {
        map.set(key, row);
      }
    }
    return map;
  }

  buildDirectoryView(
    providers: ProviderWithPlans[],
    benchMap: Map<string, BenchmarkRunRow>
  ): DisplayProvider[] {
    const flatPlans: DisplayPlan[] = [];
    const out: DisplayProvider[] = [];

    for (const p of providers) {
      const plans = (p.plans ?? []).filter(pl => pl.is_active !== false);
      const displayPlans: DisplayPlan[] = [];

      for (const plan of plans) {
        const dp = this.planToDisplayPlan(plan, benchMap);
        displayPlans.push(dp);
        flatPlans.push(dp);
      }

      out.push({
        id: p.slug,
        name: p.name,
        plans: displayPlans
      });
    }

    const maxTps = Math.max(1, ...flatPlans.map(x => x.tps));
    for (const prov of out) {
      for (const pl of prov.plans) {
        pl.tpsPercent = maxTps > 0 ? Math.min(100, Math.round((pl.tps / maxTps) * 100)) : 0;
      }
    }

    return out;
  }

  private planToDisplayPlan(plan: PlanWithRelations, benchMap: Map<string, BenchmarkRunRow>): DisplayPlan {
    const joins = plan.plan_models ?? [];
    const modelNames = joins
      .map(j => j.models?.name)
      .filter((n): n is string => !!n);
    const modelsLabel = modelNames.length ? modelNames.join(' / ') : '—';

    let bestTps = 0;
    let bestQ: string | null = null;
    for (const j of joins) {
      const key = `${plan.id}\0${j.model_id}`;
      const run = benchMap.get(key);
      if (run?.tps != null && run.tps > bestTps) {
        bestTps = run.tps;
        bestQ = run.quantization;
      }
    }

    const qInfo = this.quantizationDisplay(bestQ);
    const subtitle =
      plan.description?.trim().split('\n')[0]?.slice(0, 80) ||
      plan.slug.replace(/-/g, ' ').toUpperCase();

    return {
      id: plan.slug,
      name: plan.name,
      subtitle,
      models: modelsLabel,
      tps: Math.round(bestTps * 10) / 10,
      tpsPercent: 0,
      quantization: qInfo.label,
      quantizationStatus: qInfo.status,
      price: this.formatPrice(plan),
      period: '/ Month'
    };
  }

  formatPrice(plan: PlanWithRelations): string {
    if (plan.price_per_month == null) {
      return '—';
    }
    const cur = (plan.currency || 'USD').toUpperCase();
    if (cur === 'USD') {
      return `$${plan.price_per_month.toFixed(2)}`;
    }
    return `${plan.price_per_month.toFixed(2)} ${cur}`;
  }

  private quantizationDisplay(raw: string | null): { label: string; status: 'scam' | 'verified' } {
    if (!raw?.trim()) {
      return { label: 'NOT MEASURED', status: 'verified' };
    }
    const u = raw.toUpperCase();
    const suspicious =
      u.includes('INT4') ||
      u.includes('INT8') ||
      u.includes('4BIT') ||
      u.includes('8BIT') ||
      u.includes('AWQ') ||
      u.includes('GPTQ');
    return {
      label: u,
      status: suspicious ? 'scam' : 'verified'
    };
  }

  /**
   * Get data from any table
   */
  async getData(table: string) {
    const { data, error } = await this.supabase.from(table).select('*');
    if (error) throw error;
    return data;
  }

  /**
   * Get single item by ID
   */
  async getById(table: string, id: string) {
    const { data, error } = await this.supabase.from(table).select('*').eq('id', id).single();
    if (error) throw error;
    return data;
  }
}
