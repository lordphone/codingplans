/**
 * Data contracts for the directory.
 *
 * `*Row` types mirror the Postgres schema (supabase/migrations) as exposed by
 * PostgREST. They are hand-written for now; swap for `supabase gen types` once
 * the schema settles. View-model types (`*View`, `Directory`) are what pages
 * consume — every derived number is computed once in `shape.ts`.
 */

// ---------------------------------------------------------------- DB rows

export interface ProviderRow {
	id: string;
	name: string;
	slug: string;
	description: string | null;
	website_url: string | null;
	logo_url: string | null;
	created_at: string;
}

export interface PlanRow {
	id: string;
	provider_id: string;
	name: string;
	slug: string;
	description: string | null;
	price_per_month: number | string | null; // numeric may arrive as string
	currency: string;
	is_active: boolean;
	url: string | null;
	advertised_limits: string | null;
}

export interface ModelRow {
	id: string;
	name: string;
	slug: string;
	description: string | null;
}

export interface PlanModelRow {
	plan_id: string;
	model_id: string;
	usage_limit: string | null;
}

export interface BenchmarkRunRow {
	id: string;
	plan_id: string;
	model_id: string;
	run_at: string;
	tps: number | null;
	ttft_s: number | null;
	aggressively_quantized: boolean | null;
	samples: number | null;
	error_rate: number | null;
	tps_p10: number | null;
	ttft_p90_s: number | null;
}

export type AuditStatus = 'pass' | 'fail' | 'inconclusive' | 'error';

export interface AuditResultRow {
	id: string;
	plan_id: string;
	model_id: string;
	run_at: string;
	test_name: string;
	family: string;
	status: AuditStatus;
	metric: string | null;
	reference_value: number | null;
	target_value: number | null;
	p_value: number | null;
	q_value: number | null;
	summary: string | null;
	reference_label: string;
	target_label: string;
	panel_id: string | null;
	details: Record<string, unknown>;
}

/** Latest non-null `aggressively_quantized` per (plan, model), any time. */
export interface QuantLatestRow {
	plan_id: string;
	model_id: string;
	aggressively_quantized: boolean;
	run_at: string;
}

/** Everything the shaper needs; produced by Supabase or by fixtures. */
export interface RawData {
	providers: ProviderRow[];
	plans: PlanRow[]; // active only
	models: ModelRow[];
	planModels: PlanModelRow[];
	/** benchmark_runs within the rolling window */
	benchmarkRuns: BenchmarkRunRow[];
	quantLatest: QuantLatestRow[];
	/** rows of the latest_audit_results view */
	latestAudits: AuditResultRow[];
	/** count of audit_results rows with run_at in the rolling window */
	auditRuns30d: number;
}

// ---------------------------------------------------------------- views

export type DataSource = 'supabase' | 'fixtures' | 'unconfigured';
export type QuantStatus = 'aggressive' | 'standard' | 'untested';
export type Verdict = 'verified' | 'flagged' | 'partial' | 'untested';

export interface ModelView {
	id: string;
	name: string;
	slug: string;
	description: string | null;
}

export interface SeriesPoint {
	/** UTC day, ISO date `YYYY-MM-DD` */
	day: string;
	tps: number | null;
	ttft: number | null;
	runs: number;
}

export interface AuditView {
	testName: string;
	family: string;
	status: AuditStatus;
	metric: string | null;
	referenceValue: number | null;
	targetValue: number | null;
	pValue: number | null;
	qValue: number | null;
	summary: string | null;
	referenceLabel: string;
	targetLabel: string;
	panelId: string | null;
	runAt: string;
}

export interface Integrity {
	pass: number;
	fail: number;
	inconclusive: number;
	error: number;
	total: number;
	verdict: Verdict;
}

export interface PerfSummary {
	/** 30-day mean of per-run TPS */
	tps: number | null;
	/** 30-day mean of per-run TTFT (seconds) */
	ttft: number | null;
	tpsP10: number | null;
	ttftP90: number | null;
	errorRate: number | null;
	runs: number;
	lastRunAt: string | null;
}

export interface PlanModelView {
	model: ModelView;
	usageLimit: string | null;
	perf: PerfSummary;
	quant: QuantStatus;
	integrity: Integrity;
	audits: AuditView[];
	series: SeriesPoint[];
}

export interface PlanView {
	id: string;
	slug: string;
	name: string;
	description: string | null;
	pricePerMonth: number | null;
	currency: string;
	url: string | null;
	advertisedLimits: string | null;
	provider: { slug: string; name: string };
	models: PlanModelView[];
	/** median across models of the 30-day mean TPS */
	medianTps: number | null;
	medianTtft: number | null;
	integrity: Integrity;
	lastMeasuredAt: string | null;
}

export interface ProviderView {
	id: string;
	slug: string;
	name: string;
	description: string | null;
	websiteUrl: string | null;
	plans: PlanView[];
}

export interface DirectoryStats {
	providers: number;
	plans: number;
	models: number;
	auditRuns30d: number;
	benchmarkRuns30d: number;
	plansFlagged: number;
	plansVerified: number;
}

export interface Directory {
	source: DataSource;
	generatedAt: string;
	windowDays: number;
	providers: ProviderView[];
	models: ModelView[];
	stats: DirectoryStats;
}
