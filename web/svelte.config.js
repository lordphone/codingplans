import adapter from '@sveltejs/adapter-static';

// GitHub Pages serves the site from /codingplans; CI sets BASE_PATH=/codingplans.
// Local builds default to the domain root. Normalise away a trailing slash.
const base = (process.env.BASE_PATH ?? '').replace(/\/+$/, '');

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			// GitHub Pages serves 404.html for unknown paths; the SPA shell then
			// renders +error.svelte client-side.
			fallback: '404.html',
			strict: true
		}),
		paths: { base },
		prerender: {
			// With no published data (Supabase not configured) the dynamic routes
			// have zero entries; that is an expected, valid state.
			handleUnseenRoutes: 'ignore'
		}
	}
};

export default config;
