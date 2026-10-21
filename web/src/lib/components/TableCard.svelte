<script lang="ts">
	import type { Snippet } from 'svelte';

	/** Bordered card that scrolls its table horizontally instead of the page. */
	let {
		children,
		caption,
		class: className = ''
	}: { children: Snippet; caption?: string; class?: string } = $props();
</script>

<div
	class={['overflow-hidden rounded-sm border border-border bg-panel shadow-sm', className]}
	role={caption ? 'region' : undefined}
	aria-label={caption}
>
	<div class="overflow-x-auto overscroll-x-contain">
		{@render children()}
	</div>
</div>
