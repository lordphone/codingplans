/**
 * Build-time reads from Supabase (PostgREST) with the public anon key.
 * Any error throws — a failed fetch must fail the prerender, never publish an
 * empty site silently.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type {
	AuditResultRow,
	BenchmarkRunRow,
	ModelRow,
	PlanModelRow,
	PlanRow,
	ProviderRow,
	QuantLatestRow,
	RawData
} from './types';

const PAGE = 1000; // PostgREST default max-rows

type ProviderNested = ProviderRow & {
	plans: (PlanRow & { plan_models: (PlanModelRow & { models: ModelRow | null })[] })[];
};

class SupabaseLoadError extends Error {
	constructor(step: string, cause: { message: string; code?: string; details?: string | null }) {
		super(
			`[data] Supabase query failed (${step}): ${cause.message}` +
				(cause.code ? ` [${cause.code}]` : '') +
				(cause.details ? ` — ${cause.details}` : '')
		);
		this.name = 'SupabaseLoadError';
	}
}

/** Page through a query until a short page comes back. */
async function fetchAll<T>(
	step: string,
	page: (
		from: number,
		to: number
	) => PromiseLike<{ data: T[] | null; error: { message: string; code?: string } | null }>
): Promise<T[]> {
	const out: T[] = [];
	for (let from = 0; ; from += PAGE) {
		const { data, error } = await page(from, from + PAGE - 1);
		if (error) throw new SupabaseLoadError(step, error);
		const rows = data ?? [];
		out.push(...rows);
		if (rows.length < PAGE) return out;
	}
}

function chunk<T>(xs: T[], n: number): T[][] {
	const out: T[][] = [];
	for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n));
	return out;
}

export async function fetchRaw(
	url: string,
	anonKey: string,
	opts: { now: Date; windowDays: number }
): Promise<RawData> {
	const db: SupabaseClient = createClient(url, anonKey, {
		auth: { persistSession: false, autoRefreshToken: false }
	});
	const since = new Date(opts.now.getTime() - opts.windowDays * 86_400_000).toISOString();

	// 1. Nested directory: providers → active plans → plan_models → models.
	const nested = await fetchAll<ProviderNested>('providers', (from, to) =>
		db
			.from('providers')
			.select(
				'id, name, slug, description, website_url, logo_url, created_at, ' +
					'plans(id, provider_id, name, slug, description, price_per_month, currency, is_active, url, advertised_limits, ' +
					'plan_models(plan_id, model_id, usage_limit, models(id, name, slug, description)))'
			)
			.eq('plans.is_active', true)
			.order('name')
			.range(from, to)
			.returns<ProviderNested[]>()
	);

	const providers: ProviderRow[] = [];
	const plans: PlanRow[] = [];
	const planModels: PlanModelRow[] = [];
	const models = new Map<string, ModelRow>();
	for (const p of nested) {
		const { plans: nestedPlans, ...prov } = p;
		providers.push(prov);
		for (const pl of nestedPlans ?? []) {
			const { plan_models, ...plan } = pl;
			plans.push(plan);
			for (const pm of plan_models ?? []) {
				const { models: m, ...link } = pm;
				planModels.push(link);
				if (m) models.set(m.id, m);
			}
		}
	}

	const planIds = plans.map((p) => p.id);
	if (planIds.length === 0) {
		return {
			providers,
			plans,
			models: [...models.values()],
			planModels,
			benchmarkRuns: [],
			quantLatest: [],
			latestAudits: [],
			auditRuns30d: 0
		};
	}

	// Keep `in.(…)` filters well under URL length limits.
	const idChunks = chunk(planIds, 100);

	// 2. Benchmark runs in the rolling window.
	const benchmarkRuns: BenchmarkRunRow[] = [];
	for (const ids of idChunks) {
		benchmarkRuns.push(
			...(await fetchAll<BenchmarkRunRow>('benchmark_runs', (from, to) =>
				db
					.from('benchmark_runs')
					.select(
						'id, plan_id, model_id, run_at, tps, ttft_s, aggressively_quantized, samples, error_rate, tps_p10, ttft_p90_s'
					)
					.in('plan_id', ids)
					.gte('run_at', since)
					.order('run_at', { ascending: true })
					.order('id')
					.range(from, to)
			))
		);
	}

	// 3. Latest non-null quantization verdict per (plan, model), any time.
	const quantLatest = new Map<string, QuantLatestRow>();
	for (const ids of idChunks) {
		const rows = await fetchAll<QuantLatestRow>('benchmark_runs.quant', (from, to) =>
			db
				.from('benchmark_runs')
				.select('plan_id, model_id, aggressively_quantized, run_at')
				.in('plan_id', ids)
				.not('aggressively_quantized', 'is', null)
				.order('run_at', { ascending: false })
				.order('id')
				.range(from, to)
		);
		for (const r of rows) {
			const k = `${r.plan_id}:${r.model_id}`;
			if (!quantLatest.has(k)) quantLatest.set(k, r);
		}
	}

	// 4. Latest audit row per (plan, model, test).
	const latestAudits: AuditResultRow[] = [];
	for (const ids of idChunks) {
		latestAudits.push(
			...(await fetchAll<AuditResultRow>('latest_audit_results', (from, to) =>
				db
					.from('latest_audit_results')
					.select('*')
					.in('plan_id', ids)
					.order('plan_id')
					.order('model_id')
					.order('test_name')
					.range(from, to)
			))
		);
	}

	// 5. Audit volume in the window (headline KPI).
	const { count, error: countError } = await db
		.from('audit_results')
		.select('id', { count: 'exact', head: true })
		.gte('run_at', since);
	if (countError) throw new SupabaseLoadError('audit_results.count', countError);

	return {
		providers,
		plans,
		models: [...models.values()],
		planModels,
		benchmarkRuns,
		quantLatest: [...quantLatest.values()],
		latestAudits,
		auditRuns30d: count ?? 0
	};
}
