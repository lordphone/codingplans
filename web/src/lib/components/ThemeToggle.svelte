<script lang="ts">
	type Theme = 'system' | 'light' | 'dark';
	let theme = $state<Theme>('system');

	$effect(() => {
		try {
			const t = localStorage.getItem('theme');
			if (t === 'light' || t === 'dark') theme = t;
		} catch {
			/* storage unavailable: stay on system */
		}
	});

	function cycle() {
		theme = theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system';
		const root = document.documentElement;
		if (theme === 'system') delete root.dataset.theme;
		else root.dataset.theme = theme;
		try {
			if (theme === 'system') localStorage.removeItem('theme');
			else localStorage.setItem('theme', theme);
		} catch {
			/* ignore */
		}
	}

	const label = $derived(
		theme === 'system' ? 'Theme: system' : theme === 'light' ? 'Theme: light' : 'Theme: dark'
	);
</script>

<button
	type="button"
	onclick={cycle}
	class="inline-flex size-8 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-sunken hover:text-ink"
	aria-label={label}
	title={label}
>
	<svg viewBox="0 0 20 20" class="size-[18px]" fill="none" stroke="currentColor" stroke-width="1.6">
		{#if theme === 'light'}
			<circle cx="10" cy="10" r="3.5" />
			<path
				d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M4.7 15.3 6 14M14 6l1.3-1.3"
				stroke-linecap="round"
			/>
		{:else if theme === 'dark'}
			<path d="M15.5 12.3A6.5 6.5 0 0 1 7.7 4.5a6.5 6.5 0 1 0 7.8 7.8Z" stroke-linejoin="round" />
		{:else}
			<circle cx="10" cy="10" r="6.5" />
			<path d="M10 3.5a6.5 6.5 0 0 1 0 13Z" fill="currentColor" stroke="none" />
		{/if}
	</svg>
</button>
