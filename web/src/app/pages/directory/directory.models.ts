/** `untested`: no `benchmark_runs.quantization` on file for this plan+model yet. */
export type QuantizationStatus = 'scam' | 'verified' | 'untested';

/** One grid row: one model on a plan. */
export interface DirectoryModelRow {
  rowId: string;
  /** DB `models.id` (UUID); used when hydrating plan metrics from directory snapshot. */
  modelId: string;
  /** Route segment; same as DB `models.slug`. */
  modelSlug: string;
  modelName: string;
  /** Placeholder; DB `plan_models.usage_limit` not shown in UI for now. */
  usageLabel: string;
  tps: number;
  ttftS: number | null;
  quantization: string;
  quantizationStatus: QuantizationStatus;
}

export interface DirectoryPlan {
  id: string;
  name: string;
  subtitle: string;
  price: string;
  period: string;
  modelRows: DirectoryModelRow[];
}

export interface DirectoryProvider {
  /** Route segment; same as DB `providers.slug`. */
  id: string;
  name: string;
  plans: DirectoryPlan[];
}
