import { loadDirectory, summarizePlan } from '$lib/data/index.server';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const dir = await loadDirectory();
	return {
		source: dir.source,
		windowDays: dir.windowDays,
		stats: dir.stats,
		models: dir.models,
		providers: dir.providers
			.filter((p) => p.plans.length)
			.map((p) => ({ slug: p.slug, name: p.name })),
		plans: dir.providers.flatMap((p) => p.plans.map(summarizePlan))
	};
};
