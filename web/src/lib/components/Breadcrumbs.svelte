<script lang="ts">
	/** `href` values must already be resolved with `resolve()` by the caller. */
	let { items }: { items: { label: string; href?: string }[] } = $props();
</script>

<nav aria-label="Breadcrumb" class="mb-6">
	<ol
		class="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] tracking-wider uppercase"
	>
		{#each items as item, i (i)}
			<li class="flex items-center gap-2">
				{#if i > 0}<span aria-hidden="true" class="text-border-strong">/</span>{/if}
				{#if item.href}
					<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved by caller -->
					<a href={item.href} class="text-muted hover:text-accent-interactive">{item.label}</a>
				{:else}
					<span aria-current="page" class="text-primary">{item.label}</span>
				{/if}
			</li>
		{/each}
	</ol>
</nav>
