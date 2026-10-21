// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	/** ISO timestamp of the build (injected by vite.config.ts). */
	const __BUILD_TIME__: string;
	/** 'fixtures' when built from sample data, otherwise 'live'. */
	const __DATA_SOURCE__: 'fixtures' | 'live';
}

export {};
