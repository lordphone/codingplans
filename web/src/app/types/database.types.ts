/**
 * Row shapes for Supabase `public.*` tables.
 * Will be replaced by `supabase gen types typescript --linked` (npm run db:types) once linked.
 * Keep only DB-table interfaces here; embed/derived shapes live in `database.shapes.ts`.
 */

export interface Provider {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  website_url: string | null;
  logo_url: string | null;
  created_at: string;
}

export interface Plan {
  id: string;
  provider_id: string;
  name: string;
  slug: string;
  description: string | null;
  price_per_month: number | null;
  currency: string;
  is_active: boolean;
}

export interface Model {
  id: string;
  name: string;
  slug: string;
  description: string | null;
}

export interface PlanModel {
  plan_id: string;
  model_id: string;
  usage_limit?: string | null;
}

/**
 * One benchmark run for a plan + model (wide metrics).
 * `aggressively_quantized` is boolean: true = sub-8-bit quant detected,
 * false = standard (>=8-bit), null = untested.
 */
export interface BenchmarkRun {
  id: string;
  plan_id: string;
  model_id: string;
  run_at: string;
  tps: number | null;
  ttft_s: number | null;
  aggressively_quantized: boolean | null;
}
