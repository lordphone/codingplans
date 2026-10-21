import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
	// Same sources SvelteKit uses for $env/dynamic/public: .env files + process.env.
	const env = { ...loadEnv(mode, process.cwd(), 'PUBLIC_'), ...process.env };
	return {
		plugins: [tailwindcss(), sveltekit()],
		define: {
			// Build-time constants so the layout (and the 404 fallback shell) need no data load.
			__BUILD_TIME__: JSON.stringify(new Date().toISOString()),
			__DATA_SOURCE__: JSON.stringify(env.PUBLIC_DATA_SOURCE === 'fixtures' ? 'fixtures' : 'live')
		}
	};
});
