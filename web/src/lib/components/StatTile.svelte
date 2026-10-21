<script lang="ts">
	let {
		label,
		value,
		hint,
		tone = 'default'
	}: {
		label: string;
		value: string;
		hint?: string;
		tone?: 'default' | 'negative' | 'positive';
	} = $props();
</script>

<div class="flex min-w-0 flex-col gap-2 bg-panel p-4 sm:p-5">
	<dt class="text-eyebrow text-muted">{label}</dt>
	<dd
		class={[
			'font-mono text-3xl leading-none font-semibold tracking-tight tabular sm:text-4xl',
			tone === 'negative'
				? 'text-tertiary'
				: tone === 'positive'
					? 'text-secondary'
					: 'text-primary'
		]}
	>
		{value}
	</dd>
	{#if hint}
		<dd class="text-xs text-muted">{hint}</dd>
	{/if}
</div>
