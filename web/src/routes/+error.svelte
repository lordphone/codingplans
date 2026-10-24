<script lang="ts">
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>{page.status} — {site.name}</title>
</svelte:head>

<div class="mx-auto max-w-xl px-4 py-24 text-center sm:px-6">
	<p class="num text-sm text-muted">{page.status}</p>
	<h1 class="mt-2 text-3xl font-semibold">
		{page.status === 404 ? 'Page not found' : 'Something went wrong'}
	</h1>
	<p class="mt-3 text-ink-2">{page.error?.message}</p>
	<a class="link mt-6 inline-block" href={resolve('/')}>Back to the start</a>
</div>
