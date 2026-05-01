/** Quantization run row: only runs with a non-null `aggressively_quantized` value (no `untested` rows). */
export type PlanQuantRunStatus = 'aggressive' | 'standard';

export interface PlanPerformanceDayPoint {
  /** UTC calendar day YYYY-MM-DD */
  dayKey: string;
  /** Short axis label, e.g. 4/06 */
  label: string;
  /** Latest benchmark `run_at` in this UTC day (for chart hover). */
  latestRunAtIso: string | null;
  avgTps: number | null;
  avgTtftS: number | null;
}

export interface PlanQuantRunRow {
  runAtIso: string;
  dayLabel: string;
  timeLabel: string;
  status: PlanQuantRunStatus;
}

export interface PlanPerformanceModelBlock {
  modelId: string;
  modelName: string;
  modelSlug: string;
  tpsSeries: PlanPerformanceDayPoint[];
  ttftSeries: PlanPerformanceDayPoint[];
  quantRuns: PlanQuantRunRow[];
}

export interface PlanPerformancePage {
  providerName: string;
  providerSlug: string;
  planName: string;
  planSlug: string;
  planSubtitle: string;
  priceLabel: string;
  periodLabel: string;
  models: PlanPerformanceModelBlock[];
}
