<script lang="ts">
	import { onMount } from 'svelte';

	type Theme = 'light' | 'dark';
	let theme = $state<Theme>('light');

	function effective(): Theme {
		const set = document.documentElement.dataset.theme;
		if (set === 'light' || set === 'dark') return set;
		return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
	}

	onMount(() => {
		theme = effective();
		const mq = window.matchMedia('(prefers-color-scheme: dark)');
		const sync = () => (theme = effective());
		mq.addEventListener('change', sync);
		return () => mq.removeEventListener('change', sync);
	});

	function toggle() {
		theme = theme === 'dark' ? 'light' : 'dark';
		document.documentElement.dataset.theme = theme;
		try {
			localStorage.setItem('theme', theme);
		} catch {
			/* storage unavailable: choice lasts for this page view */
		}
	}
</script>

<button
	type="button"
	onclick={toggle}
	class="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-border text-muted hover:border-accent-interactive hover:text-primary"
	aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
	title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
>
	{#if theme === 'dark'}
		<svg
			viewBox="0 0 16 16"
			width="14"
			height="14"
			aria-hidden="true"
			fill="none"
			stroke="currentColor"
			stroke-width="1.5"
		>
			<circle cx="8" cy="8" r="3" />
			<path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1" />
		</svg>
	{:else}
		<svg
			viewBox="0 0 16 16"
			width="14"
			height="14"
			aria-hidden="true"
			fill="none"
			stroke="currentColor"
			stroke-width="1.5"
		>
			<path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
		</svg>
	{/if}
</button>
