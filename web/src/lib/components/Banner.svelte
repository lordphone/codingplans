<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<div
	class="border-b border-primary bg-primary px-4 py-1.5 text-center font-mono text-[11px] tracking-wider text-on-primary uppercase"
	role="note"
>
	{@render children()}
</div>
