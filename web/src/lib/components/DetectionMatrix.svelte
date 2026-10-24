<script lang="ts">
	import type { LabFamily, LabResult } from '#lib/data.ts';
	import { fmtEffect, fmtRequests, result } from '#lib/labstats.ts';

	let {
		family,
		selected = $bindable(),
		probeOrder
	}: { family: LabFamily; selected: string; probeOrder: string[] } = $props();

	const probes = $derived(probeOrder.filter((p) => p in family.probes));
	const honestRows = $derived(
		family.variants.filter((v) => v.kind === 'honest' && v.id !== family.reference)
	);
	const cutRows = $derived(family.variants.filter((v) => v.kind === 'cut'));

	// Sequential blue by how cheap detection is: fewer requests = darker. Log scale
	// between the smallest and largest budgets that occur in this family.
	const budgets = $derived(
		family.results.map((r) => r.requests_for_95).filter((n): n is number => n != null)
	);
	const lo = $derived(Math.log10(Math.max(1, Math.min(...budgets, 10))));
	const hi = $derived(Math.log10(Math.max(...budgets, 100)));
	const ramp = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'];
	function shade(n: number) {
		const t = hi === lo ? 1 : 1 - (Math.log10(n) - lo) / (hi - lo);
		return ramp[Math.min(ramp.length - 1, Math.max(0, Math.round(t * (ramp.length - 1))))];
	}
	const darkText = (c: string) => ramp.indexOf(c) < 3;

	function tip(r: LabResult | undefined, probe: string) {
		if (!r) return 'not run';
		if (r.inconclusive) return `inconclusive: ${r.inconclusive}`;
		const name = family.probes[probe].effect_name;
		return `${name} ${fmtEffect(r.effect, name)} (margin ${r.margin == null ? '—' : fmtEffect(r.margin, name)}), p = ${r.p_value < 0.001 ? '<0.001' : r.p_value.toFixed(3)}`;
	}
</script>

<div class="card overflow-x-auto">
	<table class="w-full min-w-[760px] border-separate border-spacing-0 text-sm">
		<thead>
			<tr>
				<th
					class="sticky left-0 z-10 bg-surface px-4 py-3 text-left text-xs font-medium text-muted"
				>
					Setup
				</th>
				{#each probes as p (p)}
					<th class="px-1.5 py-3 text-center text-xs font-medium text-muted">
						<span class="block leading-tight">{family.probes[p].title}</span>
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			<tr>
				<td
					colspan={probes.length + 1}
					class="border-t border-line bg-sunken/60 px-4 py-1.5 text-xs font-medium text-ink-2"
				>
					Honest variations: every probe should pass
				</td>
			</tr>
			{#each honestRows as v (v.id)}
				<tr
					class="cursor-pointer transition-colors hover:bg-sunken/50 {selected === v.id
						? 'bg-accent-wash/60'
						: ''}"
					onclick={() => (selected = v.id)}
				>
					<th
						scope="row"
						class="sticky left-0 z-10 border-t border-line bg-inherit px-4 py-2 text-left font-normal"
					>
						<button
							type="button"
							class="text-left hover:text-accent"
							onclick={() => (selected = v.id)}>{v.label}</button
						>
					</th>
					{#each probes as p (p)}
						{@const r = result(family, v.id, p)}
						<td class="border-t border-line px-1.5 py-1.5 text-center" title={tip(r, p)}>
							{#if !r || r.inconclusive}
								<span class="text-muted">—</span>
							{:else if r.flagged}
								<span
									class="inline-flex items-center gap-1 rounded bg-bad-wash px-1.5 py-0.5 text-xs font-medium text-bad-ink"
								>
									<svg
										viewBox="0 0 16 16"
										class="size-3"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										aria-hidden="true"
										><path d="M8 4.5v4.5M8 11.5v.01" stroke-linecap="round" /></svg
									>false alarm
								</span>
							{:else}
								<span class="inline-flex items-center gap-1 text-xs text-good-ink">
									<svg
										viewBox="0 0 16 16"
										class="size-3"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										aria-hidden="true"
										><path
											d="m3.5 8.5 3 3 6-7"
											stroke-linecap="round"
											stroke-linejoin="round"
										/></svg
									>pass
								</span>
							{/if}
						</td>
					{/each}
				</tr>
			{/each}
			<tr>
				<td
					colspan={probes.length + 1}
					class="border-t border-line bg-sunken/60 px-4 py-1.5 text-xs font-medium text-ink-2"
				>
					Corner-cuts: requests (to both endpoints) needed to detect it 95% of the time
				</td>
			</tr>
			{#each cutRows as v (v.id)}
				<tr
					class="cursor-pointer transition-colors hover:bg-sunken/50 {selected === v.id
						? 'bg-accent-wash/60'
						: ''}"
					onclick={() => (selected = v.id)}
				>
					<th
						scope="row"
						class="sticky left-0 z-10 border-t border-line bg-inherit px-4 py-2 text-left font-normal"
					>
						<button
							type="button"
							class="text-left hover:text-accent"
							onclick={() => (selected = v.id)}
						>
							{v.label}
							<span class="block text-[11px] text-muted">{v.cut}</span>
						</button>
					</th>
					{#each probes as p (p)}
						{@const r = result(family, v.id, p)}
						<td class="border-t border-line px-1 py-1 text-center" title={tip(r, p)}>
							{#if !r || r.inconclusive}
								<span class="text-muted">—</span>
							{:else if r.requests_for_95 != null}
								{@const c = shade(r.requests_for_95)}
								<span
									class="num inline-block min-w-14 rounded px-1.5 py-1 text-xs font-medium"
									style:background={c}
									style:color={darkText(c) ? '#0b0b0b' : '#ffffff'}
									>{fmtRequests(r.requests_for_95)}</span
								>
							{:else if r.flagged}
								<span
									class="num inline-block min-w-14 rounded border border-accent/40 px-1.5 py-0.5 text-xs text-ink-2"
									>&gt;{fmtRequests(r.curve.at(-1)?.requests)}</span
								>
							{:else}
								<span class="text-xs text-muted">not seen</span>
							{/if}
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>
<div class="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-2">
	<span class="flex items-center gap-2">
		Fewer requests
		<span class="flex">
			{#each [...ramp].reverse() as c (c)}<span
					class="h-3 w-5 first:rounded-l last:rounded-r"
					style:background={c}
				></span>{/each}
		</span>
		more requests
	</span>
	<span
		><span class="num rounded border border-accent/40 px-1">&gt;N</span> flagged on the full panel, below
		95% on every subsample</span
	>
	<span><span class="text-muted">not seen</span>: within the margin or not significant</span>
	<span>Hover a cell for effect, margin and p-value. Click a row for its power curves.</span>
</div>
