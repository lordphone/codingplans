import { error } from '@sveltejs/kit';
import { findProvider, loadDirectory, summarizePlan } from '$lib/data/index.server';
import type { EntryGenerator, PageServerLoad } from './$types';

export const entries: EntryGenerator = async () =>
	(await loadDirectory()).providers.map((p) => ({ provider: p.slug }));

export const load: PageServerLoad = async ({ params }) => {
	const provider = await findProvider(params.provider);
	if (!provider) error(404, `No provider “${params.provider}”.`);
	const { windowDays } = await loadDirectory();
	return { windowDays, provider: { ...provider, plans: provider.plans.map(summarizePlan) } };
};
