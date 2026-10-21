/**
 * Single entry point for page data. Runs at build time (prerender) only —
 * import it from `+page.server.ts` files, never from client code.
 *
 * Source selection:
 *   PUBLIC_DATA_SOURCE=fixtures            → src/lib/data/fixtures.ts (sample data)
 *   PUBLIC_SUPABASE_URL + _ANON_KEY set    → live Supabase (errors fail the build)
 *   otherwise                              → empty directory ("unconfigured")
 */
import { env } from '$env/dynamic/public';
import { emptyRaw, shape, WINDOW_DAYS } from './shape';
import type { Directory, PlanView, ProviderView } from './types';

let cached: Promise<Directory> | undefined;

async function build(): Promise<Directory> {
	const now = new Date();
	const generatedAt = now.toISOString();

	if (env.PUBLIC_DATA_SOURCE === 'fixtures') {
		const { fixtureRaw } = await import('./fixtures');
		return shape(fixtureRaw(now), { source: 'fixtures', generatedAt });
	}

	const url = env.PUBLIC_SUPABASE_URL?.trim();
	const key = env.PUBLIC_SUPABASE_ANON_KEY?.trim();
	if (!url || !key) {
		console.warn(
			'[data] PUBLIC_SUPABASE_URL / PUBLIC_SUPABASE_ANON_KEY not set — building with empty states.'
		);
		return shape(emptyRaw(), { source: 'unconfigured', generatedAt });
	}

	const { fetchRaw } = await import('./supabase.server');
	const raw = await fetchRaw(url, key, { now, windowDays: WINDOW_DAYS });
	return shape(raw, { source: 'supabase', generatedAt });
}

/** Memoised per build process so every prerendered page sees identical numbers. */
export function loadDirectory(): Promise<Directory> {
	cached ??= build().catch((err) => {
		console.error(err);
		throw err;
	});
	return cached;
}

export async function findProvider(slug: string): Promise<ProviderView | undefined> {
	return (await loadDirectory()).providers.find((p) => p.slug === slug);
}

export async function findPlan(
	providerSlug: string,
	planSlug: string
): Promise<PlanView | undefined> {
	return (await findProvider(providerSlug))?.plans.find((p) => p.slug === planSlug);
}

/** Drop chart series / audit detail for list pages to keep __data.json small. */
export function summarizePlan(plan: PlanView): PlanView {
	return {
		...plan,
		models: plan.models.map((m) => ({ ...m, series: [], audits: [] }))
	};
}

export type { Directory, PlanView, ProviderView };
