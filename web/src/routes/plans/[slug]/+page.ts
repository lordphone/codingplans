import { error } from '@sveltejs/kit';
import { catalog } from '#lib/data.ts';
import type { EntryGenerator, PageLoad } from './$types';

export const entries: EntryGenerator = () => catalog.plans.map((p) => ({ slug: p.slug }));

export const load: PageLoad = ({ params }) => {
	const plan = catalog.plans.find((p) => p.slug === params.slug);
	if (!plan) error(404, 'Unknown plan');
	return { plan };
};
