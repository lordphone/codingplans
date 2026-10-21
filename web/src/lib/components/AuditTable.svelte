<script lang="ts">
	import { resolve } from '$app/paths';
	import { familyLabel, TEST_BY_ID } from '$lib/content/tests';
	import type { AuditView } from '$lib/data/types';
	import { fmtDate, fmtMetric, fmtP } from '$lib/format';
	import StatusBadge from './StatusBadge.svelte';
	import TableCard from './TableCard.svelte';

	let { audits, caption }: { audits: AuditView[]; caption: string } = $props();
	const th = 'text-nav px-3 py-2.5 text-muted';
</script>

<TableCard>
	<table class="data-table min-w-[1080px]">
		<caption class="sr-only">{caption}</caption>
		<thead>
			<tr>
				<th scope="col" class={th}>Test</th>
				<th scope="col" class={th}>Family</th>
				<th scope="col" class={th}>Status</th>
				<th scope="col" class={th}>Metric</th>
				<th scope="col" class={[th, 'text-right']}>Reference</th>
				<th scope="col" class={[th, 'text-right']}>Plan</th>
				<th scope="col" class={[th, 'text-right']}>q-value</th>
				<th scope="col" class={th}>Run</th>
				<th scope="col" class={th}>Summary</th>
			</tr>
		</thead>
		<tbody>
			{#each audits as a (a.testName)}
				{@const spec = TEST_BY_ID.get(a.testName)}
				<tr class={a.status === 'fail' ? 'bg-tertiary-container/40' : ''}>
					<td>
						<a
							class="link font-medium whitespace-nowrap"
							href={resolve(`/methodology/#${a.testName}`)}>{spec?.name ?? a.testName}</a
						>
						<div class="font-mono text-[11px] text-muted">{a.testName}</div>
					</td>
					<td class="text-xs whitespace-nowrap text-muted">{familyLabel(a.family)}</td>
					<td><StatusBadge kind="status" value={a.status} /></td>
					<td class="font-mono text-[11px] text-muted">{a.metric ?? '—'}</td>
					<td class="text-right font-mono tabular" title={a.referenceLabel}>
						{fmtMetric(a.referenceValue)}
					</td>
					<td
						class={[
							'text-right font-mono tabular',
							a.status === 'fail' ? 'font-semibold text-tertiary' : 'text-primary'
						]}
						title={a.targetLabel}
					>
						{fmtMetric(a.targetValue)}
					</td>
					<td class="text-right font-mono tabular text-muted">{fmtP(a.qValue)}</td>
					<td class="font-mono text-[11px] whitespace-nowrap text-muted">
						<time datetime={a.runAt}>{fmtDate(a.runAt)}</time>
					</td>
					<td class="max-w-sm min-w-64 text-xs leading-relaxed">{a.summary ?? '—'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</TableCard>
