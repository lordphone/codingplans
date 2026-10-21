<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, children }: { title: string; children?: Snippet } = $props();
</script>

<div class="rounded-sm border border-dashed border-border-strong bg-panel px-6 py-12 text-center">
	<p class="text-eyebrow text-muted">No data</p>
	<p class="mt-2 text-lg font-semibold text-primary">{title}</p>
	{#if children}
		<div class="mx-auto mt-2 max-w-prose text-sm text-muted">{@render children()}</div>
	{/if}
</div>
