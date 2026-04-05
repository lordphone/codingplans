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
