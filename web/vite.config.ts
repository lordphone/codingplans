import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// GitHub Pages serves the site from /codingplans; BASE_PATH='' for a root deploy.
const base = (process.env.BASE_PATH ??
	(process.env.NODE_ENV === 'production' ? '/codingplans' : '')) as '' | `/${string}`;

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter({ fallback: '404.html' }),
			paths: { base },
			prerender: { handleHttpError: 'fail', handleMissingId: 'fail' }
		})
	],
	// The site reads the repo-level data/ directory at build time.
	server: { fs: { allow: ['..'] } }
});
