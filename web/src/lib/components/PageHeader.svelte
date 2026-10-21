<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		eyebrow,
		title,
		variant = 'display',
		children,
		aside
	}: {
		eyebrow?: string;
		title: string;
		variant?: 'display' | 'entity';
		children?: Snippet;
		aside?: Snippet;
	} = $props();
</script>

<header
	class="flex flex-col gap-6 border-b border-border pb-8 md:flex-row md:items-end md:justify-between"
>
	<div class="min-w-0">
		{#if eyebrow}
			<p class="mb-3 text-eyebrow text-muted">{eyebrow}</p>
		{/if}
		<h1
			class={['break-words text-primary', variant === 'display' ? 'text-display' : 'text-entity']}
		>
			{title}
		</h1>
		{#if children}
			<div class="mt-4 max-w-2xl text-base leading-relaxed text-on-surface/80">
				{@render children()}
			</div>
		{/if}
	</div>
	{#if aside}
		<div class="shrink-0">{@render aside()}</div>
	{/if}
</header>
