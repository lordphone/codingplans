/** Provider detail page view model (Supabase-backed). */

export type ProviderPageQuantColor = 'tertiary' | 'secondary' | 'neutral';

export interface ProviderPageModelRow {
  id: string;
  name: string;
  quantization: string;
  quantizationColor: ProviderPageQuantColor;
  tps: string;
  ttft: string;
}

export interface ProviderPagePlan {
  id: string;
  name: string;
  tierId: string;
  price: string;
  period: string;
  models: ProviderPageModelRow[];
}

export interface ProviderPageData {
  providerName: string;
  lastUpdated: string;
  plans: ProviderPagePlan[];
}
