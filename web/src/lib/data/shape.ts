/**
 * Pure shaping: raw table rows → page view models. No I/O.
 *
 * Semantics (keep in sync with AGENTS.md "Directory query semantics"):
 * - active plans only, nested provider → plan → plan_models → model
 * - TPS/TTFT: mean over the rolling window per (plan, model)
 * - quantization: latest non-null `aggressively_quantized` per (plan, model)
 * - integrity: counts over `latest_audit_results`; any fail → flagged,
 *   all pass (≥1) → verified, no rows → untested, otherwise partial
 */
import type {
	AuditResultRow,
	AuditView,
	BenchmarkRunRow,
	DataSource,
	Directory,
	Integrity,
	ModelView,
	PerfSummary,
	PlanModelView,
	PlanView,
	ProviderView,
	QuantStatus,
	RawData,
	SeriesPoint,
	Verdict
} from './types';

export const WINDOW_DAYS = 30;

const key = (planId: string, modelId: string) => `${planId}:${modelId}`;

function mean(values: (number | null | undefined)[]): number | null {
	const xs = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
	return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}

export function median(values: (number | null | undefined)[]): number | null {
	const xs = values
		.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
		.sort((a, b) => a - b);
	if (!xs.length) return null;
	const mid = Math.floor(xs.length / 2);
	return xs.length % 2 ? xs[mid] : (xs[mid - 1] + xs[mid]) / 2;
}

function groupBy<T>(items: T[], k: (t: T) => string): Map<string, T[]> {
	const m = new Map<string, T[]>();
	for (const item of items) {
		const id = k(item);
		const bucket = m.get(id);
		if (bucket) bucket.push(item);
		else m.set(id, [item]);
	}
	return m;
}

export function verdictOf(c: Omit<Integrity, 'verdict' | 'total'>): Verdict {
	const total = c.pass + c.fail + c.inconclusive + c.error;
	if (c.fail > 0) return 'flagged';
	if (total === 0) return 'untested';
	if (c.pass === total) return 'verified';
	return 'partial';
}

function integrityOf(audits: { status: string }[]): Integrity {
	const c = { pass: 0, fail: 0, inconclusive: 0, error: 0 };
	for (const a of audits) {
		if (a.status in c) c[a.status as keyof typeof c]++;
	}
	return { ...c, total: audits.length, verdict: verdictOf(c) };
}

function sumIntegrity(parts: Integrity[]): Integrity {
	const c = { pass: 0, fail: 0, inconclusive: 0, error: 0 };
	for (const p of parts) {
		c.pass += p.pass;
		c.fail += p.fail;
		c.inconclusive += p.inconclusive;
		c.error += p.error;
	}
	return { ...c, total: c.pass + c.fail + c.inconclusive + c.error, verdict: verdictOf(c) };
}

function perfOf(runs: BenchmarkRunRow[]): PerfSummary {
	const sorted = [...runs].sort((a, b) => a.run_at.localeCompare(b.run_at));
	return {
		tps: mean(runs.map((r) => r.tps)),
		ttft: mean(runs.map((r) => r.ttft_s)),
		tpsP10: mean(runs.map((r) => r.tps_p10)),
		ttftP90: mean(runs.map((r) => r.ttft_p90_s)),
		errorRate: mean(runs.map((r) => r.error_rate)),
		runs: runs.length,
		lastRunAt: sorted.length ? sorted[sorted.length - 1].run_at : null
	};
}

/** Daily (UTC) means for charting. */
function seriesOf(runs: BenchmarkRunRow[]): SeriesPoint[] {
	const byDay = groupBy(runs, (r) => r.run_at.slice(0, 10));
	return [...byDay.entries()]
		.sort(([a], [b]) => a.localeCompare(b))
		.map(([day, rs]) => ({
			day,
			tps: mean(rs.map((r) => r.tps)),
			ttft: mean(rs.map((r) => r.ttft_s)),
			runs: rs.length
		}));
}

function auditView(r: AuditResultRow): AuditView {
	return {
		testName: r.test_name,
		family: r.family,
		status: r.status,
		metric: r.metric,
		referenceValue: r.reference_value,
		targetValue: r.target_value,
		pValue: r.p_value,
		qValue: r.q_value,
		summary: r.summary,
		referenceLabel: r.reference_label,
		targetLabel: r.target_label,
		panelId: r.panel_id,
		runAt: r.run_at
	};
}

const STATUS_ORDER: Record<string, number> = { fail: 0, error: 1, inconclusive: 2, pass: 3 };

function toNumber(v: number | string | null): number | null {
	if (v === null || v === undefined) return null;
	const n = typeof v === 'number' ? v : Number(v);
	return Number.isFinite(n) ? n : null;
}

export function shape(
	raw: RawData,
	opts: { source: DataSource; generatedAt: string; windowDays?: number }
): Directory {
	const windowDays = opts.windowDays ?? WINDOW_DAYS;
	const models = new Map<string, ModelView>(
		raw.models.map((m) => [
			m.id,
			{ id: m.id, name: m.name, slug: m.slug, description: m.description }
		])
	);
	const runsBy = groupBy(raw.benchmarkRuns, (r) => key(r.plan_id, r.model_id));
	const quantBy = new Map(raw.quantLatest.map((q) => [key(q.plan_id, q.model_id), q]));
	const auditsBy = groupBy(raw.latestAudits, (a) => key(a.plan_id, a.model_id));
	const pmBy = groupBy(raw.planModels, (pm) => pm.plan_id);
	const plansBy = groupBy(raw.plans, (p) => p.provider_id);

	const providers: ProviderView[] = raw.providers
		.map((prov) => {
			const plans: PlanView[] = (plansBy.get(prov.id) ?? [])
				.filter((p) => p.is_active)
				.map((plan) => {
					const pms: PlanModelView[] = (pmBy.get(plan.id) ?? [])
						.filter((pm) => models.has(pm.model_id))
						.map((pm) => {
							const k = key(plan.id, pm.model_id);
							const runs = runsBy.get(k) ?? [];
							const q = quantBy.get(k);
							const quant: QuantStatus = q
								? q.aggressively_quantized
									? 'aggressive'
									: 'standard'
								: 'untested';
							const audits = (auditsBy.get(k) ?? [])
								.map(auditView)
								.sort(
									(a, b) =>
										(STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
										a.testName.localeCompare(b.testName)
								);
							return {
								model: models.get(pm.model_id)!,
								usageLimit: pm.usage_limit,
								perf: perfOf(runs),
								quant,
								integrity: integrityOf(audits),
								audits,
								series: seriesOf(runs)
							};
						})
						.sort((a, b) => a.model.name.localeCompare(b.model.name));

					const lastTimes = pms
						.flatMap((m) => [m.perf.lastRunAt, ...m.audits.map((a) => a.runAt)])
						.filter((t): t is string => !!t)
						.sort();

					return {
						id: plan.id,
						slug: plan.slug,
						name: plan.name,
						description: plan.description,
						pricePerMonth: toNumber(plan.price_per_month),
						currency: plan.currency || 'USD',
						url: plan.url,
						advertisedLimits: plan.advertised_limits,
						provider: { slug: prov.slug, name: prov.name },
						models: pms,
						medianTps: median(pms.map((m) => m.perf.tps)),
						medianTtft: median(pms.map((m) => m.perf.ttft)),
						integrity: sumIntegrity(pms.map((m) => m.integrity)),
						lastMeasuredAt: lastTimes.length ? lastTimes[lastTimes.length - 1] : null
					};
				})
				.sort(
					(a, b) =>
						(a.pricePerMonth ?? Infinity) - (b.pricePerMonth ?? Infinity) ||
						a.name.localeCompare(b.name)
				);
			return {
				id: prov.id,
				slug: prov.slug,
				name: prov.name,
				description: prov.description,
				websiteUrl: prov.website_url,
				plans
			};
		})
		.sort((a, b) => a.name.localeCompare(b.name));

	const allPlans = providers.flatMap((p) => p.plans);
	const offeredModelIds = new Set(allPlans.flatMap((p) => p.models.map((m) => m.model.id)));

	return {
		source: opts.source,
		generatedAt: opts.generatedAt,
		windowDays,
		providers,
		models: [...models.values()]
			.filter((m) => offeredModelIds.has(m.id))
			.sort((a, b) => a.name.localeCompare(b.name)),
		stats: {
			providers: providers.filter((p) => p.plans.length).length,
			plans: allPlans.length,
			models: offeredModelIds.size,
			auditRuns30d: raw.auditRuns30d,
			benchmarkRuns30d: raw.benchmarkRuns.length,
			plansFlagged: allPlans.filter((p) => p.integrity.verdict === 'flagged').length,
			plansVerified: allPlans.filter((p) => p.integrity.verdict === 'verified').length
		}
	};
}

export function emptyRaw(): RawData {
	return {
		providers: [],
		plans: [],
		models: [],
		planModels: [],
		benchmarkRuns: [],
		quantLatest: [],
		latestAudits: [],
		auditRuns30d: 0
	};
}
