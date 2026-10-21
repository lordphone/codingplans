<script lang="ts">
	import type { PlanModelView } from '$lib/data/types';
	import { DASH, fmtNum } from '$lib/format';
	import BarMini from './BarMini.svelte';
	import StatusBadge from './StatusBadge.svelte';
	import TableCard from './TableCard.svelte';

	let { models, caption, maxTps }: { models: PlanModelView[]; caption: string; maxTps?: number } =
		$props();

	const max = $derived(maxTps ?? Math.max(1, ...models.map((m) => m.perf.tps ?? 0)));
	const th = 'text-nav px-3 py-2.5 text-muted';
</script>

<TableCard>
	<table class="data-table min-w-[1000px] table-fixed">
		<caption class="sr-only">{caption}</caption>
		<thead>
			<tr>
				<th scope="col" class={[th, 'w-48']}>Model</th>
				<th scope="col" class={[th, 'w-40']}>Usage limit</th>
				<th scope="col" class={th}>TPS · 30d</th>
				<th scope="col" class={[th, 'w-20 text-right']}>TPS p10</th>
				<th scope="col" class={[th, 'w-20 text-right']}>TTFT</th>
				<th scope="col" class={[th, 'w-20 text-right']}>Errors</th>
				<th scope="col" class={[th, 'w-44']}>Quantization</th>
				<th scope="col" class={[th, 'w-40']}>Integrity</th>
			</tr>
		</thead>
		<tbody>
			{#each models as m (m.model.id)}
				<tr>
					<td>
						<div class="font-semibold text-primary">{m.model.name}</div>
						<div class="font-mono text-[11px] text-muted">{m.model.slug}</div>
					</td>
					<td class="text-xs">
						{#if m.usageLimit}{m.usageLimit}{:else}<span class="text-muted">Not published</span
							>{/if}
					</td>
					<td>
						<div class="flex items-center gap-3">
							<span class="w-12 shrink-0 text-right font-mono tabular">{fmtNum(m.perf.tps, 1)}</span
							>
							<BarMini value={m.perf.tps} {max} class="max-w-24" />
						</div>
					</td>
					<td class="text-right font-mono tabular text-muted">{fmtNum(m.perf.tpsP10, 1)}</td>
					<td class="text-right font-mono tabular">
						{m.perf.ttft === null ? DASH : `${fmtNum(m.perf.ttft, 2)} s`}
					</td>
					<td class="text-right font-mono tabular text-muted">
						{m.perf.errorRate === null ? DASH : `${fmtNum(m.perf.errorRate * 100, 1)}%`}
					</td>
					<td><StatusBadge kind="quant" value={m.quant} /></td>
					<td>
						<div class="flex items-center gap-2">
							<StatusBadge kind="verdict" value={m.integrity.verdict} />
							{#if m.integrity.total}
								<span class="font-mono text-[11px] tabular whitespace-nowrap text-muted"
									>{m.integrity.pass}/{m.integrity.total}</span
								>
							{/if}
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</TableCard>
