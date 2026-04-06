/** `untested`: no `benchmark_runs.quantization` on file for this plan+model yet. */
export type QuantizationStatus = 'scam' | 'verified' | 'untested';

/** One grid row: one model on a plan. */
export interface DirectoryModelRow {
  rowId: string;
  modelName: string;
  /** No dedicated DB column yet; placeholder until limits exist in schema. */
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
