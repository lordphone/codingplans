import { loadDirectory } from '$lib/data/index.server';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const dir = await loadDirectory();
	const groups = dir.models
		.map((model) => ({
			model,
			rows: dir.providers
				.flatMap((prov) =>
					prov.plans.flatMap((plan) =>
						plan.models
							.filter((pm) => pm.model.id === model.id)
							.map((pm) => ({
								provider: { slug: prov.slug, name: prov.name },
								plan: { slug: plan.slug, name: plan.name },
								perf: pm.perf,
								quant: pm.quant,
								verdict: pm.integrity.verdict
							}))
					)
				)
				.sort((a, b) => (b.perf.tps ?? -1) - (a.perf.tps ?? -1))
		}))
		.filter((g) => g.rows.length);
	return { windowDays: dir.windowDays, groups };
};
