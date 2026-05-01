/** Row shapes for Supabase `public.*` tables (UUIDs as strings in JSON). */

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

/** Junction: which models are included in a plan. */
export interface PlanModel {
  plan_id: string;
  model_id: string;
  /** Free-form usage limit copy for this plan+model (optional in API embeds). */
  usage_limit?: string | null;
}

/**
 * One benchmark run for a plan + model (wide metrics, Option B).
 * Nullable metric columns = not measured on this run.
 * `aggressively_quantized` is boolean: true = sub-8-bit quant detected, false = standard (>=8-bit), null = untested.
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

// --- Nested `.select()` result shapes (PostgREST embeds) ---

export interface PlanModelWithModel extends PlanModel {
  models: Model;
}

export interface PlanWithModels extends Plan {
  plan_models: PlanModelWithModel[];
}

export interface ProviderWithPlansAndModels extends Provider {
  plans: PlanWithModels[];
}

// --- Display types for UI (not database tables) ---

export interface DisplayPlan {
  id: string;
  name: string;
  subtitle: string;
  models: string;
  tps: number;
  tpsPercent: number;
  quantizationStatus: 'aggressive' | 'standard';
  price: string;
  period: string;
}

export interface DisplayProvider {
  id: string;
  name: string;
  providerId: string;
  plans: DisplayPlan[];
}
