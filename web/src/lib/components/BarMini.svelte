<script lang="ts">
	/** Horizontal minibar; decorative — the number beside it carries the value. */
	let {
		value,
		max,
		color = 'primary',
		class: className = ''
	}: {
		value: number | null;
		max: number;
		color?: 'primary' | 'throughput' | 'latency';
		class?: string;
	} = $props();

	const pct = $derived(
		value === null || !Number.isFinite(value) || max <= 0
			? 0
			: Math.max(2, Math.min(100, (value / max) * 100))
	);
	const fill = $derived(
		color === 'throughput'
			? 'bg-chart-throughput'
			: color === 'latency'
				? 'bg-chart-latency'
				: 'bg-primary'
	);
</script>

<span
	class={['relative block h-1.5 w-full overflow-hidden rounded-sm bg-neutral', className]}
	aria-hidden="true"
>
	{#if value !== null}
		<span class={['absolute inset-y-0 left-0 rounded-sm', fill]} style:width="{pct}%"></span>
	{/if}
</span>
