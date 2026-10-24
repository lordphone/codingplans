// Build-time view of the repository's data/ directory (the public dataset).
// Everything is imported eagerly, so prerendered pages contain the numbers and
// the site never calls an API at runtime.

export type Provider = { slug: string; name: string; maker_of?: string; url: string };
export type Model = {
	slug: string;
	name: string;
	maker: string;
	open_weights: boolean;
	notes?: string;
};
export type Plan = {
	slug: string;
	provider: string;
	name: string;
	price: number;
	currency: string;
	limits: string;
	models: string[];
	tos_risk: 'high' | 'medium' | 'low' | 'unknown';
	tos_note?: string;
};
export type EndpointInfo = {
	slug: string;
	role: string;
	provider: string | null;
	model: string | null;
	api_model: string;
	base_url: string;
};
export type Catalog = {
	snapshot: string;
	providers: Provider[];
	models: Model[];
	plans: Plan[];
	audits: { plan: string; target: EndpointInfo; reference: EndpointInfo }[];
};

export type AuditStatus = 'match' | 'gap' | 'inconclusive';
export type AuditVerdict = {
	probe: string;
	title?: string;
	detects?: string;
	skipped?: string;
	effect?: number;
	effect_name?: string;
	p_value?: number;
	q_value?: number;
	margin?: number | null;
	flagged?: boolean;
	inconclusive?: string | null;
	n_items?: number;
	requests?: number;
	reference?: Record<string, unknown>;
	target?: Record<string, unknown>;
	detail?: Record<string, unknown>;
};
export type AuditResult = {
	plan: string;
	target: EndpointInfo;
	reference: EndpointInfo;
	tier: string;
	started_at: string;
	finished_at: string;
	status: AuditStatus;
	verdicts: AuditVerdict[];
};

export type CurvePoint = {
	items: number;
	requests: number;
	rate: number | null;
	rate_significance_only: number | null;
	median_effect: number | null;
};
export type LabResult = {
	variant: string;
	probe: string;
	effect: number;
	p_value: number;
	n_items: number;
	inconclusive: string | null;
	margin: number | null;
	flagged: boolean;
	requests_for_95: number | null;
	error_rate: number;
	detail: Record<string, unknown>;
	reference: Record<string, unknown>;
	target: Record<string, unknown>;
	curve: CurvePoint[];
};
export type LabVariant = {
	id: string;
	kind: 'honest' | 'cut';
	cut: string | null;
	label: string;
	model: string;
	args: string[];
	proxy: Record<string, unknown>;
};
export type LabProbe = {
	title: string;
	detects: string;
	effect_name: string;
	margin: number | null;
	config: Record<string, unknown>;
};
export type LabFamily = {
	family: string;
	name: string;
	params_b: number;
	reference: string;
	generated_at: string;
	engine: { vllm: string | null; gpu: string | null };
	alpha: number;
	headroom: number;
	variants: LabVariant[];
	probes: Record<string, LabProbe>;
	results: LabResult[];
};

const catalogFiles = import.meta.glob<Catalog>('../../../data/catalog.json', {
	eager: true,
	import: 'default'
});
const auditFiles = import.meta.glob<AuditResult>('../../../data/audits/*/*/*.json', {
	eager: true,
	import: 'default'
});
const labFiles = import.meta.glob<LabFamily>('../../../data/lab/qwen*.json', {
	eager: true,
	import: 'default'
});

export const catalog: Catalog = Object.values(catalogFiles)[0];

/** Every published audit, newest first. */
export const audits: AuditResult[] = Object.values(auditFiles).sort((a, b) =>
	b.started_at.localeCompare(a.started_at)
);

/** Lab families, largest model first. */
export const lab: LabFamily[] = Object.values(labFiles).sort((a, b) => b.params_b - a.params_b);

export const providerBySlug = new Map(catalog.providers.map((p) => [p.slug, p]));
export const modelBySlug = new Map(catalog.models.map((m) => [m.slug, m]));

export function latestAudit(plan: string, target: string): AuditResult | undefined {
	return audits.find((a) => a.plan === plan && a.target.slug === target);
}

export function auditsForPlan(plan: string) {
	return catalog.audits
		.filter((a) => a.plan === plan)
		.map((a) => ({ ...a, latest: latestAudit(a.plan, a.target.slug) }));
}

export function planStatus(plan: string): AuditStatus | 'untested' {
	const rows = auditsForPlan(plan);
	const done = rows.filter((r) => r.latest);
	if (!done.length) return 'untested';
	if (done.some((r) => r.latest!.status === 'gap')) return 'gap';
	if (done.every((r) => r.latest!.status === 'match') && done.length === rows.length)
		return 'match';
	return 'inconclusive';
}

/** Path of a data file as served by the site (see scripts/sync-data.mjs). */
export const dataPath = (rel: string) => `/data/${rel}`;
