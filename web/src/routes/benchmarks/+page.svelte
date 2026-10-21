<script lang="ts">
	import { resolve } from '$app/paths';
	import BarMini from '$lib/components/BarMini.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import TableCard from '$lib/components/TableCard.svelte';
	import { DASH, fmtNum } from '$lib/format';
	import { SITE } from '$lib/site';

	let { data } = $props();
	const th = 'text-nav px-3 py-2.5 text-muted';
</script>

<svelte:head>
	<title>Benchmarks · {SITE.name}</title>
	<meta
		name="description"
		content="Cross-plan speed leaderboard: {data.windowDays}-day throughput and time-to-first-token for each model across coding plans."
	/>
</svelte:head>

<PageHeader eyebrow="Speed leaderboard · rolling {data.windowDays} days" title="Benchmarks">
	<p>
		The same model, served by different plans. Ranked by mean output throughput over the window; p10
		shows how slow the slow sessions get. Speed is only half the story — check each plan’s integrity
		verdict before reading a fast number as a good one.
	</p>
	{#snippet aside()}
		{#if data.groups.length}
			<nav aria-label="Models" class="flex flex-wrap gap-2 md:max-w-xs md:justify-end">
				{#each data.groups as g (g.model.id)}
					<a
						href="#{g.model.slug}"
						class="rounded-sm border border-border-strong bg-panel px-2.5 py-1.5 font-mono text-[11px] text-on-surface hover:border-accent-interactive hover:text-primary"
						>{g.model.name}</a
					>
				{/each}
			</nav>
		{/if}
	{/snippet}
</PageHeader>

<div class="mt-10 flex flex-col gap-14">
	{#each data.groups as g (g.model.id)}
		{@const max = Math.max(1, ...g.rows.map((r) => r.perf.tps ?? 0))}
		<section id={g.model.slug} aria-labelledby="h-{g.model.slug}" class="scroll-mt-28">
			<div class="mb-4 flex flex-wrap items-baseline justify-between gap-2">
				<h2 id="h-{g.model.slug}" class="text-2xl font-semibold tracking-tight text-primary">
					{g.model.name}
				</h2>
				<p class="font-mono text-[11px] text-muted">
					{g.model.slug} · {g.rows.length}
					{g.rows.length === 1 ? 'plan' : 'plans'}
				</p>
			</div>
			<TableCard>
				<table class="data-table min-w-[1000px] table-fixed">
					<caption class="sr-only">{g.model.name}: plans ranked by mean throughput</caption>
					<thead>
						<tr>
							<th scope="col" class={[th, 'w-12 text-right']}>#</th>
							<th scope="col" class={[th, 'w-56']}>Plan</th>
							<th scope="col" class={th}>Mean TPS</th>
							<th scope="col" class={[th, 'w-24 text-right']}>TPS p10</th>
							<th scope="col" class={[th, 'w-24 text-right']}>TTFT</th>
							<th scope="col" class={[th, 'w-24 text-right']}>TTFT p90</th>
							<th scope="col" class={[th, 'w-20 text-right']}>Errors</th>
							<th scope="col" class={[th, 'w-44']}>Quant</th>
							<th scope="col" class={[th, 'w-32']}>Integrity</th>
						</tr>
					</thead>
					<tbody>
						{#each g.rows as r, i (r.provider.slug + r.plan.slug)}
							<tr>
								<td class="text-right font-mono tabular text-muted"
									>{r.perf.tps === null ? DASH : i + 1}</td
								>
								<td>
									<a
										class="link font-semibold"
										href={resolve(`/providers/${r.provider.slug}/${r.plan.slug}/`)}>{r.plan.name}</a
									>
									<div class="text-xs text-muted">{r.provider.name}</div>
								</td>
								<td>
									<div class="flex items-center gap-3">
										<span
											class="w-12 shrink-0 text-right font-mono font-semibold tabular text-primary"
											>{fmtNum(r.perf.tps, 1)}</span
										>
										<BarMini value={r.perf.tps} {max} color="throughput" class="h-2" />
									</div>
								</td>
								<td class="text-right font-mono tabular text-muted">{fmtNum(r.perf.tpsP10, 1)}</td>
								<td class="text-right font-mono tabular">
									{r.perf.ttft === null ? DASH : `${fmtNum(r.perf.ttft, 2)} s`}
								</td>
								<td class="text-right font-mono tabular text-muted">
									{r.perf.ttftP90 === null ? DASH : `${fmtNum(r.perf.ttftP90, 2)} s`}
								</td>
								<td class="text-right font-mono tabular text-muted">
									{r.perf.errorRate === null ? DASH : `${fmtNum(r.perf.errorRate * 100, 1)}%`}
								</td>
								<td><StatusBadge kind="quant" value={r.quant} /></td>
								<td><StatusBadge kind="verdict" value={r.verdict} /></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</TableCard>
		</section>
	{:else}
		<EmptyState title="No measurements published yet">
			<p>Speed results appear here once benchmark runs are published.</p>
		</EmptyState>
	{/each}
</div>
