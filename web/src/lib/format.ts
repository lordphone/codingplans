/**
 * Display formatting. All dates render in UTC so prerendered HTML and the
 * hydrated client agree byte for byte.
 */
import type { AuditStatus, QuantStatus, Verdict } from '$lib/data/types';

export const DASH = '—';

export function fmtNum(v: number | null | undefined, digits = 1): string {
	if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
	return v.toLocaleString('en-US', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	});
}

/** Compact value for audit metrics (rates as-is, big numbers grouped). */
export function fmtMetric(v: number | null | undefined): string {
	if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
	const abs = Math.abs(v);
	if (abs !== 0 && abs < 0.001) return v.toExponential(1);
	if (abs >= 100) return fmtNum(v, 0);
	if (abs >= 10) return fmtNum(v, 1);
	const out = fmtNum(v, 3).replace(/\.?0+$/, '');
	return out === '' || out === '-0' ? '0' : out;
}

export function fmtP(v: number | null | undefined): string {
	if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
	if (v < 0.0001) return '<0.0001';
	return v.toFixed(v < 0.01 ? 4 : 3);
}

export function fmtPrice(v: number | null, currency = 'USD'): string {
	if (v === null) return DASH;
	try {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency,
			minimumFractionDigits: Number.isInteger(v) ? 0 : 2,
			maximumFractionDigits: 2
		}).format(v);
	} catch {
		return `${v} ${currency}`;
	}
}

export function fmtDate(iso: string | null | undefined): string {
	if (!iso) return DASH;
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return DASH;
	return d.toLocaleDateString('en-US', {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		timeZone: 'UTC'
	});
}

export function fmtDateShort(iso: string): string {
	const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
	return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

export function fmtDateTime(iso: string | null | undefined): string {
	if (!iso) return DASH;
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return DASH;
	return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
	verified: 'Verified',
	flagged: 'Flagged',
	partial: 'Partial',
	untested: 'Untested'
};

export const STATUS_LABEL: Record<AuditStatus, string> = {
	pass: 'Pass',
	fail: 'Fail',
	inconclusive: 'Inconclusive',
	error: 'Error'
};

export const QUANT_LABEL: Record<QuantStatus, string> = {
	standard: 'Standard',
	aggressive: 'Aggressive quant',
	untested: 'Untested'
};
