<script lang="ts">
	import '../app.css';
	import Banner from '$lib/components/Banner.svelte';
	import SiteFooter from '$lib/components/SiteFooter.svelte';
	import SiteNav from '$lib/components/SiteNav.svelte';
	import { IS_SAMPLE } from '$lib/site';

	let { children } = $props();
</script>

<a
	href="#main"
	class="sr-only z-50 rounded-sm bg-primary px-3 py-2 text-sm text-on-primary focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
	>Skip to content</a
>

<div class="flex min-h-screen flex-col">
	<header class="sticky top-0 z-40">
		{#if IS_SAMPLE}
			<Banner>Sample data — not real measurements</Banner>
		{/if}
		<SiteNav />
	</header>

	<main id="main" class="mx-auto w-full max-w-7xl flex-1 px-4 pt-10 sm:px-6 sm:pt-14 lg:px-12">
		{@render children()}
	</main>

	<SiteFooter />
</div>
