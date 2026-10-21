<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	import { SITE } from '$lib/site';

	const notFound = $derived(page.status === 404);
</script>

<svelte:head>
	<title>{notFound ? 'Not found' : 'Error'} · {SITE.name}</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<section class="mx-auto max-w-2xl py-12">
	<p class="text-eyebrow text-muted">HTTP {page.status}</p>
	<h1 class="mt-3 text-display text-primary">{notFound ? 'Not found' : 'Error'}</h1>
	<div class="mt-8">
		<ErrorAlert title={notFound ? 'No page at this address.' : 'Something went wrong.'}>
			<p class="font-mono text-xs break-words">{page.error?.message ?? 'Unknown error'}</p>
		</ErrorAlert>
	</div>
	<p class="mt-8 text-sm">
		<a class="link" href={resolve('/')}>← Back to the directory</a>
	</p>
</section>
