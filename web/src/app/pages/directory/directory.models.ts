export type QuantizationStatus = 'scam' | 'verified';

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
  id: string;
  name: string;
  providerId: string;
  plans: DirectoryPlan[];
}
