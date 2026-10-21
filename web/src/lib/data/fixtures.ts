/**
 * SAMPLE DATA — not real measurements.
 *
 * Deterministic fixtures for `PUBLIC_DATA_SOURCE=fixtures` builds: realistic
 * shapes, invented numbers. Timestamps are relative to `now` so the rolling
 * 30-day window always has data. Values are seeded, so a rebuild on the same
 * day produces the same page.
 */
import { TESTS } from '$lib/content/tests';
import type {
	AuditResultRow,
	AuditStatus,
	BenchmarkRunRow,
	ModelRow,
	PlanModelRow,
	PlanRow,
	ProviderRow,
	QuantLatestRow,
	RawData
} from './types';

function mulberry32(seed: number) {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = a;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

function hash(s: string): number {
	let h = 2166136261;
	for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
	return h >>> 0;
}

/** Stable fake UUID from a string. */
function uuid(s: string): string {
	const r = mulberry32(hash(s));
	const hex = Array.from({ length: 32 }, () => Math.floor(r() * 16).toString(16)).join('');
	return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

const round = (x: number, d = 2) => Math.round(x * 10 ** d) / 10 ** d;

// ---------------------------------------------------------------- catalog

const MODELS = (
	[
		{
			slug: 'glm-5',
			name: 'GLM-5',
			description: 'Z.ai flagship coding model (sample entry).',
			refTps: 62,
			refTtft: 0.9,
			official: 'glm5-official'
		},
		{
			slug: 'kimi-k2.5',
			name: 'Kimi K2.5',
			description: 'Moonshot AI agentic coding model (sample entry).',
			refTps: 48,
			refTtft: 1.1,
			official: 'kimi-k2.5-official'
		},
		{
			slug: 'minimax-m2.5',
			name: 'MiniMax-M2.5',
			description: 'MiniMax coding model (sample entry).',
			refTps: 84,
			refTtft: 0.7,
			official: 'minimax-m2.5-official'
		},
		{
			slug: 'qwen3-coder-plus',
			name: 'qwen3-coder-plus',
			description: 'Alibaba Qwen coder (sample entry).',
			refTps: 72,
			refTtft: 0.8,
			official: 'qwen3-coder-plus-official'
		}
	] satisfies (Omit<ModelRow, 'id'> & { refTps: number; refTtft: number; official: string })[]
).map((m) => ({ ...m, id: uuid(`model:${m.slug}`) }));

const PROVIDERS: ProviderRow[] = (
	[
		{
			slug: 'alibaba-cloud',
			name: 'Alibaba Cloud Model Studio',
			description:
				'Multi-model coding plan bundling first- and third-party models. Sample entry for UI development.',
			website_url: 'https://www.alibabacloud.com/en/product/modelstudio'
		},
		{
			slug: 'minimax',
			name: 'MiniMax',
			description: 'Coding plan for the MiniMax M-series. Sample entry for UI development.',
			website_url: 'https://www.minimax.io'
		},
		{
			slug: 'moonshot',
			name: 'Moonshot AI (Kimi)',
			description: 'Kimi coding subscription. Sample entry for UI development.',
			website_url: 'https://www.kimi.com'
		},
		{
			slug: 'zai',
			name: 'Z.ai',
			description: 'GLM Coding Plan tiers. Sample entry for UI development.',
			website_url: 'https://z.ai'
		}
	] satisfies Omit<ProviderRow, 'id' | 'logo_url' | 'created_at'>[]
).map((p) => ({
	...p,
	id: uuid(`provider:${p.slug}`),
	logo_url: null,
	created_at: '2026-01-01T00:00:00Z'
}));

type Profile = {
	/** plan TPS as a fraction of the reference */
	speed: number;
	ttft: number;
	quant: boolean | null; // null → never measured
	audits: 'none' | 'clean' | 'mixed' | 'quantized' | 'inflated' | 'truncated';
	usage?: string | null;
};

interface PlanSeed {
	provider: string;
	slug: string;
	name: string;
	price: number;
	limits: string;
	active?: boolean;
	models: Record<string, Profile>;
}

const PLANS: PlanSeed[] = [
	{
		provider: 'alibaba-cloud',
		slug: 'alibaba-lite',
		name: 'Coding Plan Lite',
		price: 10,
		limits: '1,200 requests / 5 h (sample)',
		models: {
			'qwen3-coder-plus': { speed: 0.92, ttft: 1.2, quant: false, audits: 'mixed' },
			'glm-5': { speed: 1.08, ttft: 1.1, quant: true, audits: 'quantized', usage: null },
			'kimi-k2.5': { speed: 0.81, ttft: 1.6, quant: false, audits: 'mixed' },
			'minimax-m2.5': { speed: 0.88, ttft: 1.3, quant: null, audits: 'none' }
		}
	},
	{
		provider: 'alibaba-cloud',
		slug: 'alibaba-pro',
		name: 'Coding Plan Pro',
		price: 50,
		limits: '6,000 requests / 5 h (sample)',
		models: {
			'qwen3-coder-plus': { speed: 1.02, ttft: 0.95, quant: false, audits: 'clean' },
			'glm-5': { speed: 0.97, ttft: 1.05, quant: false, audits: 'mixed' },
			'kimi-k2.5': { speed: 0.9, ttft: 1.2, quant: null, audits: 'none' }
		}
	},
	{
		provider: 'minimax',
		slug: 'minimax-starter',
		name: 'Starter',
		price: 10,
		limits: '100 prompts / 5 h (sample)',
		models: {
			'minimax-m2.5': {
				speed: 0.74,
				ttft: 1.9,
				quant: false,
				audits: 'inflated',
				usage: '100 prompts / 5 h'
			}
		}
	},
	{
		provider: 'minimax',
		slug: 'minimax-plus',
		name: 'Plus',
		price: 20,
		limits: '300 prompts / 5 h (sample)',
		models: {
			'minimax-m2.5': {
				speed: 0.99,
				ttft: 1.0,
				quant: false,
				audits: 'clean',
				usage: '300 prompts / 5 h'
			}
		}
	},
	{
		provider: 'moonshot',
		slug: 'moonshot-basic',
		name: 'Kimi Code Basic',
		price: 19,
		limits: 'Weekly token quota (sample)',
		models: {
			'kimi-k2.5': { speed: 0.86, ttft: 1.3, quant: false, audits: 'mixed' }
		}
	},
	{
		provider: 'moonshot',
		slug: 'moonshot-pro',
		name: 'Kimi Code Pro',
		price: 49,
		limits: '5× Basic quota (sample)',
		models: {
			'kimi-k2.5': { speed: 1.04, ttft: 0.9, quant: false, audits: 'clean' }
		}
	},
	{
		provider: 'zai',
		slug: 'zai-lite',
		name: 'GLM Coding Lite',
		price: 6,
		limits: '~120 prompts / 5 h (sample)',
		models: {
			'glm-5': { speed: 0.68, ttft: 2.1, quant: false, audits: 'truncated' }
		}
	},
	{
		provider: 'zai',
		slug: 'zai-pro',
		name: 'GLM Coding Pro',
		price: 30,
		limits: '~600 prompts / 5 h (sample)',
		models: {
			'glm-5': { speed: 1.01, ttft: 0.95, quant: false, audits: 'clean' }
		}
	},
	{
		provider: 'zai',
		slug: 'zai-max',
		name: 'GLM Coding Max',
		price: 80,
		limits: '~2,400 prompts / 5 h (sample)',
		models: {
			'glm-5': { speed: 1.06, ttft: 0.85, quant: null, audits: 'none' }
		}
	},
	{
		provider: 'zai',
		slug: 'zai-legacy',
		name: 'Legacy (inactive — must not render)',
		price: 3,
		limits: '',
		active: false,
		models: { 'glm-5': { speed: 1, ttft: 1, quant: null, audits: 'none' } }
	}
];

// ---------------------------------------------------------------- audits

const METRICS: Record<
	string,
	{ metric: string; ref: number; failTo: number; jitter: number; digits?: number }
> = {
	arithmetic: { metric: 'digit_accuracy', ref: 0.972, failTo: 0.814, jitter: 0.008, digits: 3 },
	rollout_prefix: {
		metric: 'median_common_prefix_tokens',
		ref: 38,
		failTo: 6,
		jitter: 3,
		digits: 0
	},
	entropy: { metric: 'renyi2_entropy_bits', ref: 3.12, failTo: 2.41, jitter: 0.06 },
	needle_single: { metric: 'retrieval_accuracy', ref: 0.98, failTo: 0.62, jitter: 0.01, digits: 3 },
	needle_multi: { metric: 'smile_curvature', ref: 0.12, failTo: 0.31, jitter: 0.02, digits: 3 },
	needle_aggregation: {
		metric: 'count_accuracy',
		ref: 0.94,
		failTo: 0.58,
		jitter: 0.02,
		digits: 3
	},
	tool_calls: { metric: 'schema_valid_rate', ref: 0.985, failTo: 0.902, jitter: 0.006, digits: 3 },
	token_accounting: {
		metric: 'prompt_tokens_delta_pct',
		ref: 0,
		failTo: 18.4,
		jitter: 0.2,
		digits: 1
	},
	param_compliance: { metric: 'compliance_rate', ref: 1, failTo: 0.86, jitter: 0, digits: 3 },
	response_cache: { metric: 'stale_nonce_rate', ref: 0, failTo: 0.07, jitter: 0, digits: 3 },
	reasoning_budget: {
		metric: 'mean_reasoning_tokens',
		ref: 4210,
		failTo: 1630,
		jitter: 120,
		digits: 0
	},
	code_exec: { metric: 'unit_test_pass_rate', ref: 0.78, failTo: 0.61, jitter: 0.02, digits: 3 },
	performance: { metric: 'mean_tps', ref: 60, failTo: 30, jitter: 2, digits: 1 }
};

function statusesFor(kind: Profile['audits'], rnd: () => number): Map<string, AuditStatus> {
	const m = new Map<string, AuditStatus>();
	if (kind === 'none') return m;
	for (const t of TESTS) {
		let s: AuditStatus = 'pass';
		if (kind === 'mixed') {
			const r = rnd();
			s = r < 0.22 ? 'inconclusive' : r < 0.27 ? 'error' : 'pass';
		}
		if (kind === 'quantized' && (t.id === 'arithmetic' || t.id === 'entropy')) s = 'fail';
		if (kind === 'quantized' && t.id === 'needle_multi') s = 'inconclusive';
		if (kind === 'inflated' && t.id === 'token_accounting') s = 'fail';
		if (kind === 'inflated' && t.id === 'reasoning_budget') s = 'inconclusive';
		if (kind === 'truncated' && (t.id === 'needle_single' || t.id === 'needle_aggregation'))
			s = 'fail';
		if (kind === 'truncated' && t.id === 'performance') s = 'fail';
		m.set(t.id, s);
	}
	return m;
}

/** Benjamini–Hochberg adjusted p-values. */
function bh(ps: (number | null)[]): (number | null)[] {
	const idx = ps
		.map((p, i) => ({ p, i }))
		.filter((x): x is { p: number; i: number } => x.p !== null)
		.sort((a, b) => a.p - b.p);
	const n = idx.length;
	const out: (number | null)[] = ps.map(() => null);
	let prev = 1;
	for (let k = n - 1; k >= 0; k--) {
		const q = Math.min(prev, (idx[k].p * n) / (k + 1));
		prev = q;
		out[idx[k].i] = q;
	}
	return out;
}

function summaryFor(test: string, status: AuditStatus, ref: number, target: number): string {
	switch (status) {
		case 'pass':
			return 'No significant difference from the official API at FDR 0.05.';
		case 'fail':
			return `Plan diverges from reference (${target} vs ${ref}); survives BH correction.`;
		case 'inconclusive':
			return test === 'token_accounting'
				? 'Usage fields missing on too many responses to compare.'
				: 'Too few usable samples on one side; rerun scheduled.';
		case 'error':
			return 'Run aborted: repeated HTTP 429 from the plan endpoint.';
	}
}

// ---------------------------------------------------------------- build

export function fixtureRaw(now: Date): RawData {
	const day = 86_400_000;
	const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
	const modelBySlug = new Map(MODELS.map((m) => [m.slug, m]));
	const providerBySlug = new Map(PROVIDERS.map((p) => [p.slug, p]));

	const plans: PlanRow[] = [];
	const planModels: PlanModelRow[] = [];
	const benchmarkRuns: BenchmarkRunRow[] = [];
	const quantLatest: QuantLatestRow[] = [];
	const latestAudits: AuditResultRow[] = [];
	let auditRuns30d = 0;

	for (const seed of PLANS) {
		const provider = providerBySlug.get(seed.provider)!;
		const planId = uuid(`plan:${seed.slug}`);
		const active = seed.active ?? true;
		plans.push({
			id: planId,
			provider_id: provider.id,
			name: seed.name,
			slug: seed.slug,
			description: `Sample ${provider.name} tier for UI development. Prices and limits are invented.`,
			price_per_month: seed.price,
			currency: 'USD',
			is_active: active,
			url: provider.website_url,
			advertised_limits: seed.limits || null
		});

		for (const [modelSlug, prof] of Object.entries(seed.models)) {
			const model = modelBySlug.get(modelSlug)!;
			const rnd = mulberry32(hash(`${seed.slug}:${modelSlug}`));
			planModels.push({ plan_id: planId, model_id: model.id, usage_limit: prof.usage ?? null });

			// ~4 probe sessions per day for 30 days, with a few gaps and a mid-window dip.
			let lastQuant: QuantLatestRow | undefined;
			for (let d = 29; d >= 0; d--) {
				if (rnd() < 0.06) continue; // missed day
				for (let s = 0; s < 4; s++) {
					const t = today - d * day + s * 6 * 3_600_000 + Math.floor(rnd() * 3_000_000);
					if (t > now.getTime()) continue;
					const dip = d >= 11 && d <= 14 ? 0.82 : 1; // a visible incident
					const peak = s === 2 ? 0.9 : 1; // busier hour
					const tps = model.refTps * prof.speed * dip * peak * (0.92 + rnd() * 0.16);
					const ttft = model.refTtft * prof.ttft * (1 / dip) * (0.85 + rnd() * 0.35);
					const quant = prof.quant !== null && rnd() < 0.12 ? prof.quant : (null as boolean | null);
					const runAt = new Date(t).toISOString();
					benchmarkRuns.push({
						id: uuid(`run:${seed.slug}:${modelSlug}:${d}:${s}`),
						plan_id: planId,
						model_id: model.id,
						run_at: runAt,
						tps: round(tps, 1),
						ttft_s: round(ttft, 3),
						aggressively_quantized: quant,
						samples: 8,
						error_rate: round(Math.max(0, (prof.speed < 0.8 ? 0.05 : 0.01) * rnd()), 3),
						tps_p10: round(tps * (0.78 + rnd() * 0.08), 1),
						ttft_p90_s: round(ttft * (1.4 + rnd() * 0.4), 3)
					});
					if (quant !== null) {
						lastQuant = {
							plan_id: planId,
							model_id: model.id,
							aggressively_quantized: quant,
							run_at: runAt
						};
					}
				}
			}
			if (prof.quant !== null) {
				quantLatest.push(
					lastQuant ?? {
						plan_id: planId,
						model_id: model.id,
						aggressively_quantized: prof.quant,
						run_at: new Date(today - 2 * day).toISOString()
					}
				);
			}

			// Audits: an earlier run (~19 days ago) and the latest run (~3 days ago).
			const statuses = statusesFor(prof.audits, rnd);
			if (!statuses.size) continue;
			auditRuns30d += statuses.size * 2;
			const latestAt = new Date(today - 3 * day + 9 * 3_600_000).toISOString();
			const rows = TESTS.map((t) => {
				const status = statuses.get(t.id)!;
				const spec = METRICS[t.id];
				const ref =
					t.id === 'performance'
						? model.refTps
						: round(spec.ref + (rnd() - 0.5) * spec.jitter, spec.digits ?? 2);
				const target =
					t.id === 'performance'
						? round(model.refTps * prof.speed, spec.digits ?? 2)
						: status === 'fail'
							? round(spec.failTo + (rnd() - 0.5) * spec.jitter, spec.digits ?? 2)
							: round(ref + (rnd() - 0.5) * spec.jitter * 1.5, spec.digits ?? 2);
				const p =
					status === 'fail'
						? 10 ** -(3 + rnd() * 3)
						: status === 'pass'
							? 0.15 + rnd() * 0.8
							: status === 'inconclusive'
								? 0.04 + rnd() * 0.2
								: null;
				return { t, status, ref, target, p };
			});
			const qs = bh(rows.map((r) => r.p));
			rows.forEach((r, i) => {
				latestAudits.push({
					id: uuid(`audit:${seed.slug}:${modelSlug}:${r.t.id}`),
					plan_id: planId,
					model_id: model.id,
					run_at: latestAt,
					test_name: r.t.id,
					family: r.t.family,
					status: r.status,
					metric: METRICS[r.t.id].metric,
					reference_value: r.status === 'error' ? null : r.ref,
					target_value: r.status === 'error' ? null : r.target,
					p_value: r.p,
					q_value: qs[i],
					summary: summaryFor(r.t.id, r.status, r.ref, r.target),
					reference_label: model.official,
					target_label: `${modelSlug}-${seed.slug}`,
					panel_id: `${r.t.id}_v1`,
					details: {}
				});
			});
		}
	}

	// Only active plans are handed to the shaper (matches the Supabase query).
	const activeIds = new Set(plans.filter((p) => p.is_active).map((p) => p.id));
	return {
		providers: PROVIDERS,
		plans: plans.filter((p) => activeIds.has(p.id)),
		models: MODELS.map(({ id, name, slug, description }) => ({ id, name, slug, description })),
		planModels: planModels.filter((pm) => activeIds.has(pm.plan_id)),
		benchmarkRuns: benchmarkRuns.filter((r) => activeIds.has(r.plan_id)),
		quantLatest: quantLatest.filter((r) => activeIds.has(r.plan_id)),
		latestAudits: latestAudits.filter((r) => activeIds.has(r.plan_id)),
		auditRuns30d
	};
}
