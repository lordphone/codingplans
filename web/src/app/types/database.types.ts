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

export type MetricType = 'tps' | 'latency' | 'quality' | 'price';

export interface Benchmark {
  id: string;
  plan_id: string;
  model_id: string;
  metric_type: MetricType;
  value: number;
  unit: string;
  recorded_at: string;
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
  id: string;
  name: string;
  providerId: string;
  plans: DisplayPlan[];
}
