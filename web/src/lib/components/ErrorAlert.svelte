<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, children }: { title: string; children?: Snippet } = $props();
</script>

<div
	role="alert"
	class="rounded-sm border border-error-border bg-error-surface px-4 py-3 text-sm text-error-text"
>
	<p class="font-semibold">{title}</p>
	{#if children}
		<div class="mt-1">{@render children()}</div>
	{/if}
</div>
