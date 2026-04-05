export interface Provider {
  id: string;
  name: string;
  slug: string;
  description?: string;
  website_url?: string;
  logo_url?: string;
  created_at: string;
}

export interface Plan {
  id: string;
  provider_id: string;
  name: string;
  slug: string;
  description?: string;
  price_per_month?: number;
  currency: string;
  is_active: boolean;
}

export interface Model {
  id: string;
  name: string;
  slug: string;
  description?: string;
}

export interface PlanModel {
  plan_id: string;
  model_id: string;
}

/** Latest row per plan+model is resolved in the app (see SupabaseService). */
export interface BenchmarkRunRow {
  id: string;
  plan_id: string;
  model_id: string;
  tps: number | null;
  ttft_s: number | null;
  quantization: string | null;
  recorded_at: string;
}

export interface PlanModelJoin {
  model_id: string;
  models: Model | null;
}

export interface PlanWithRelations extends Plan {
  plan_models?: PlanModelJoin[] | null;
}

export interface ProviderWithPlans extends Provider {
  plans?: PlanWithRelations[] | null;
}

// Display types for UI (not database tables)
export interface DisplayPlan {
  id: string;
  name: string;
  subtitle: string;
  models: string;
  tps: number;
  tpsPercent: number;
  quantization: string;
  quantizationStatus: 'scam' | 'verified';
  price: string;
  period: string;
}

export interface DisplayProvider {
  /** URL segment: provider `slug` from the database */
  id: string;
  name: string;
  plans: DisplayPlan[];
}

export interface PlanDetailView {
  id: string;
  name: string;
  tierId: string;
  price: string;
  period: string;
  modelTarget: string;
  quantization: string;
  quantizationColor: 'tertiary' | 'secondary';
  tps: string;
  notice: string;
  isPro: boolean;
}
