import type { LabFamily, LabResult } from './data';

export function result(f: LabFamily, variant: string, probe: string): LabResult | undefined {
	return f.results.find((r) => r.variant === variant && r.probe === probe);
}

export function cuts(f: LabFamily) {
	return f.variants.filter((v) => v.kind === 'cut');
}

export function honest(f: LabFamily) {
	return f.variants.filter((v) => v.kind === 'honest' && v.id !== f.reference);
}

/** Probes that flagged a variant at the full panel. */
export function flaggedBy(f: LabFamily, variant: string): string[] {
	return f.results.filter((r) => r.variant === variant && r.flagged).map((r) => r.probe);
}

export function summary(f: LabFamily) {
	const c = cuts(f);
	const h = honest(f);
	const detected = c.filter((v) => flaggedBy(f, v.id).length > 0);
	const honestChecks = f.results.filter(
		(r) => h.some((v) => v.id === r.variant) && !r.inconclusive
	);
	const falseAlarms = honestChecks.filter((r) => r.flagged);
	return {
		cuts: c.length,
		detected: detected.length,
		missed: c.filter((v) => !detected.includes(v)).map((v) => v.label),
		honest: h.length,
		honestChecks: honestChecks.length,
		falseAlarms: falseAlarms.length
	};
}

/** Ratio of the observed effect to the probe's calibrated margin. */
export function strength(r: LabResult): number | null {
	if (r.inconclusive || r.margin == null || r.margin === 0) return null;
	return r.effect / r.margin;
}

export const fmtRequests = (n: number | null | undefined) =>
	n == null ? '—' : n >= 1000 ? `${+(n / 1000).toFixed(1)}K` : `${n}`;

export function fmtEffect(v: number, name: string) {
	if (name.includes('tokens')) return `${v >= 0 ? '+' : ''}${v.toFixed(1)}`;
	if (name.includes('accuracy') || name.includes('slowdown'))
		return `${v >= 0 ? '−' : '+'}${Math.abs(v * 100).toFixed(1)} pt`.replace(
			'pt',
			name.includes('slowdown') ? '%' : 'pt'
		);
	return v.toFixed(3);
}
