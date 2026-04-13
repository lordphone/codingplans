/** Quantization benchmark row: only measured labels (no `untested` rows). */
export type PlanQuantRunStatus = 'scam' | 'verified';

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
  label: string;
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
