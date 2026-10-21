<script lang="ts" module>
	export type SortDir = 'asc' | 'desc';
</script>

<script lang="ts">
	let {
		label,
		key,
		sortKey,
		sortDir,
		onsort,
		align = 'left',
		class: className = ''
	}: {
		label: string;
		key: string;
		sortKey: string;
		sortDir: SortDir;
		onsort: (key: string) => void;
		align?: 'left' | 'right';
		class?: string;
	} = $props();

	const active = $derived(sortKey === key);
</script>

<th
	scope="col"
	aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
	class={['px-3 py-2.5 font-semibold', align === 'right' && 'text-right', className]}
>
	<button
		type="button"
		onclick={() => onsort(key)}
		class={[
			'group inline-flex items-center gap-1 rounded-sm text-nav uppercase hover:text-primary',
			active ? 'text-primary' : 'text-muted',
			align === 'right' && 'flex-row-reverse'
		]}
	>
		{label}
		<span
			aria-hidden="true"
			class={[
				'font-mono text-[10px]',
				active ? 'opacity-100' : 'opacity-30 group-hover:opacity-70'
			]}
		>
			{active ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
		</span>
	</button>
</th>
