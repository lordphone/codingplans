import { error } from '@sveltejs/kit';
import { findPlan, findProvider, loadDirectory } from '$lib/data/index.server';
import type { EntryGenerator, PageServerLoad } from './$types';

export const entries: EntryGenerator = async () =>
	(await loadDirectory()).providers.flatMap((p) =>
		p.plans.map((plan) => ({ provider: p.slug, plan: plan.slug }))
	);

export const load: PageServerLoad = async ({ params }) => {
	const plan = await findPlan(params.provider, params.plan);
	if (!plan) error(404, `No plan “${params.plan}” for provider “${params.provider}”.`);
	const provider = (await findProvider(params.provider))!;
	const { windowDays } = await loadDirectory();
	return {
		windowDays,
		plan,
		provider: { slug: provider.slug, name: provider.name, websiteUrl: provider.websiteUrl },
		siblings: provider.plans
			.filter((p) => p.id !== plan.id)
			.map((p) => ({
				slug: p.slug,
				name: p.name,
				pricePerMonth: p.pricePerMonth,
				currency: p.currency
			}))
	};
};
