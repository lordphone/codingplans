<script lang="ts">
	import { resolve } from '$app/paths';
	import BarMini from '$lib/components/BarMini.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import SortHeader, { type SortDir } from '$lib/components/SortHeader.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import TableCard from '$lib/components/TableCard.svelte';
	import type { PlanView, Verdict } from '$lib/data/types';
	import { DASH, fmtNum, fmtPrice, VERDICT_LABEL } from '$lib/format';
	import { SITE } from '$lib/site';

	let { data } = $props();

	let query = $state('');
	let verdictFilter = $state<Verdict | 'all'>('all');
	let providerFilter = $state<string>('all');
	let sortKey = $state('verdict');
	let sortDir = $state<SortDir>('asc');

	const VERDICT_RANK: Record<Verdict, number> = {
		flagged: 0,
		partial: 1,
		untested: 2,
		verified: 3
	};
	const verdicts: Verdict[] = ['verified', 'flagged', 'partial', 'untested'];

	const sorters: Record<string, (p: PlanView) => string | number | null> = {
		provider: (p) => p.provider.name.toLowerCase(),
		plan: (p) => p.name.toLowerCase(),
		price: (p) => p.pricePerMonth,
		models: (p) => p.models.length,
		tps: (p) => p.medianTps,
		ttft: (p) => p.medianTtft,
		verdict: (p) => VERDICT_RANK[p.integrity.verdict]
	};

	function onsort(key: string) {
		if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			sortDir = key === 'tps' ? 'desc' : 'asc';
		}
	}

	const maxTps = $derived(Math.max(1, ...data.plans.map((p) => p.medianTps ?? 0)));

	const rows = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const get = sorters[sortKey];
		const dir = sortDir === 'asc' ? 1 : -1;
		return data.plans
			.filter((p) => verdictFilter === 'all' || p.integrity.verdict === verdictFilter)
			.filter((p) => providerFilter === 'all' || p.provider.slug === providerFilter)
			.filter(
				(p) =>
					!q ||
					[p.name, p.slug, p.provider.name, p.provider.slug, ...p.models.map((m) => m.model.name)]
						.join(' ')
						.toLowerCase()
						.includes(q)
			)
			.sort((a, b) => {
				const va = get(a);
				const vb = get(b);
				if (va === null && vb === null) return 0;
				if (va === null) return 1; // nulls last regardless of direction
				if (vb === null) return -1;
				const c = va < vb ? -1 : va > vb ? 1 : 0;
				return c * dir || a.provider.name.localeCompare(b.provider.name);
			});
	});

	const verdictCounts = $derived(
		Object.fromEntries(
			verdicts.map((v) => [v, data.plans.filter((p) => p.integrity.verdict === v).length])
		) as Record<Verdict, number>
	);

	const hasData = $derived(data.plans.length > 0);
	const chip =
		'inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1.5 font-mono text-[11px] tracking-wide transition-colors';
</script>

<svelte:head>
	<title>Directory · {SITE.name}</title>
	<meta name="description" content={SITE.tagline} />
</svelte:head>

<PageHeader eyebrow="Coding plan audit · rolling {data.windowDays} days" title="Directory">
	<p>
		Flat-rate AI coding plans, measured against the <strong class="font-semibold text-primary"
			>official API for the same model</strong
		>. We track speed and run a statistical test suite for quantization, model swaps, context
		truncation, broken tool calls and inflated token counts.
	</p>
</PageHeader>

<dl
	class="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border lg:grid-cols-4"
>
	<StatTile
		label="Plans tracked"
		value={String(data.stats.plans)}
		hint="{data.stats.providers} providers"
	/>
	<StatTile label="Models" value={String(data.stats.models)} hint="distinct catalog models" />
	<StatTile
		label="Audit tests · {data.windowDays}d"
		value={data.stats.auditRuns30d.toLocaleString('en-US')}
		hint="{data.stats.benchmarkRuns30d.toLocaleString('en-US')} speed probes"
	/>
	<StatTile
		label="Plans flagged"
		value={String(data.stats.plansFlagged)}
		hint="{data.stats.plansVerified} verified clean"
		tone={data.stats.plansFlagged > 0 ? 'negative' : 'default'}
	/>
</dl>

<section class="mt-12" aria-labelledby="plans-heading">
	<div class="mb-4 flex items-baseline justify-between gap-4">
		<h2 id="plans-heading" class="text-nav text-primary">All plans</h2>
		<a class="link font-mono text-xs" href={resolve('/methodology/')}>How verdicts work →</a>
	</div>

	{#if !hasData}
		<EmptyState title="No measurements published yet">
			<p>
				{#if data.source === 'unconfigured'}
					This build has no data source configured. Plans appear here once benchmark and audit
					results are published.
				{:else}
					No active plans are listed yet. Check back after the next audit cycle.
				{/if}
			</p>
		</EmptyState>
	{:else}
		<div class="flex flex-col gap-3">
			<label class="relative block">
				<span class="sr-only">Search plans, providers and models</span>
				<input
					type="search"
					bind:value={query}
					placeholder="Search plans, models…"
					autocomplete="off"
					spellcheck="false"
					class="block w-full rounded-sm border border-border-strong bg-panel py-3 pr-28 pl-4 font-mono text-sm text-primary placeholder:text-muted focus:border-accent-interactive focus:ring-1 focus:ring-accent-interactive focus:outline-none"
				/>
				<span
					class="pointer-events-none absolute inset-y-0 right-4 flex items-center font-mono text-[11px] tracking-wider text-muted uppercase"
					aria-live="polite"
				>
					{rows.length}
					{rows.length === 1 ? 'result' : 'results'}
				</span>
			</label>

			<div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-6">
				<div
					class="flex flex-wrap items-center gap-1.5"
					role="group"
					aria-label="Filter by verdict"
				>
					<span class="mr-1 text-eyebrow text-muted">Verdict</span>
					<button
						type="button"
						aria-pressed={verdictFilter === 'all'}
						onclick={() => (verdictFilter = 'all')}
						class={[
							chip,
							verdictFilter === 'all'
								? 'border-primary bg-primary text-on-primary'
								: 'border-border-strong bg-panel text-on-surface hover:border-primary'
						]}>All</button
					>
					{#each verdicts as v (v)}
						<button
							type="button"
							aria-pressed={verdictFilter === v}
							onclick={() => (verdictFilter = verdictFilter === v ? 'all' : v)}
							class={[
								chip,
								verdictFilter === v
									? 'border-primary bg-primary text-on-primary'
									: 'border-border-strong bg-panel text-on-surface hover:border-primary'
							]}
						>
							{VERDICT_LABEL[v]}
							<span class="opacity-60">{verdictCounts[v]}</span>
						</button>
					{/each}
				</div>
				<div
					class="flex flex-wrap items-center gap-1.5"
					role="group"
					aria-label="Filter by provider"
				>
					<span class="mr-1 text-eyebrow text-muted">Provider</span>
					<button
						type="button"
						aria-pressed={providerFilter === 'all'}
						onclick={() => (providerFilter = 'all')}
						class={[
							chip,
							providerFilter === 'all'
								? 'border-primary bg-primary text-on-primary'
								: 'border-border-strong bg-panel text-on-surface hover:border-primary'
						]}>All</button
					>
					{#each data.providers as p (p.slug)}
						<button
							type="button"
							aria-pressed={providerFilter === p.slug}
							onclick={() => (providerFilter = providerFilter === p.slug ? 'all' : p.slug)}
							class={[
								chip,
								providerFilter === p.slug
									? 'border-primary bg-primary text-on-primary'
									: 'border-border-strong bg-panel text-on-surface hover:border-primary'
							]}>{p.name}</button
						>
					{/each}
				</div>
			</div>

			<TableCard caption="Plans directory" class="hidden md:block">
				<table class="data-table min-w-[880px]">
					<caption class="sr-only">
						Coding plans with 30-day speed and integrity verdict. Column headers sort the table.
					</caption>
					<thead>
						<tr>
							<SortHeader label="Provider" key="provider" {sortKey} {sortDir} {onsort} />
							<SortHeader label="Plan" key="plan" {sortKey} {sortDir} {onsort} />
							<SortHeader label="Price/mo" key="price" align="right" {sortKey} {sortDir} {onsort} />
							<SortHeader label="Models" key="models" {sortKey} {sortDir} {onsort} />
							<SortHeader label="Median TPS" key="tps" class="w-44" {sortKey} {sortDir} {onsort} />
							<SortHeader label="TTFT" key="ttft" align="right" {sortKey} {sortDir} {onsort} />
							<SortHeader label="Integrity" key="verdict" {sortKey} {sortDir} {onsort} />
						</tr>
					</thead>
					<tbody>
						{#each rows as plan (plan.id)}
							<tr class="group relative hover:bg-neutral/60">
								<td class="text-muted">
									<a
										class="link relative z-10 text-sm text-on-surface"
										href={resolve(`/providers/${plan.provider.slug}/`)}>{plan.provider.name}</a
									>
								</td>
								<td>
									<a
										class="font-semibold whitespace-nowrap text-primary group-hover:text-accent-interactive after:absolute after:inset-0 after:content-['']"
										href={resolve(`/providers/${plan.provider.slug}/${plan.slug}/`)}>{plan.name}</a
									>
									<div class="font-mono text-[11px] text-muted">{plan.slug}</div>
								</td>
								<td class="text-right font-mono tabular">
									{fmtPrice(plan.pricePerMonth, plan.currency)}
								</td>
								<td>
									<span class="font-mono text-xs tabular text-muted">{plan.models.length} ·</span>
									<span class="text-xs"
										>{plan.models.map((m) => m.model.name).join(', ') || DASH}</span
									>
								</td>
								<td>
									<div class="flex items-center gap-3">
										<span class="w-12 shrink-0 text-right font-mono tabular">
											{fmtNum(plan.medianTps, 1)}
										</span>
										<BarMini value={plan.medianTps} max={maxTps} class="max-w-28" />
									</div>
								</td>
								<td class="text-right font-mono tabular">
									{plan.medianTtft === null ? DASH : `${fmtNum(plan.medianTtft, 2)} s`}
								</td>
								<td>
									<div class="flex items-center gap-2">
										<StatusBadge kind="verdict" value={plan.integrity.verdict} />
										{#if plan.integrity.total}
											<span class="font-mono text-[11px] tabular whitespace-nowrap text-muted">
												{plan.integrity.pass}/{plan.integrity.total} pass{#if plan.integrity.fail}
													· <span class="text-tertiary">{plan.integrity.fail} fail</span>{/if}
											</span>
										{/if}
									</div>
								</td>
							</tr>
						{:else}
							<tr>
								<td colspan="7" class="py-10 text-center text-sm text-muted">
									No plans match these filters.
									<button
										type="button"
										class="link ml-1"
										onclick={() => {
											query = '';
											verdictFilter = 'all';
											providerFilter = 'all';
										}}>Clear filters</button
									>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</TableCard>

			<!-- Phone layout: stacked cards (the table needs ~880px). -->
			<div class="flex flex-col gap-3 md:hidden">
				<label class="flex items-center justify-end gap-2 font-mono text-[11px] text-muted">
					<span class="text-eyebrow">Sort</span>
					<select
						class="rounded-sm border border-border-strong bg-panel px-2 py-1.5 font-mono text-xs text-primary focus:border-accent-interactive focus:outline-none"
						value="{sortKey}:{sortDir}"
						onchange={(e) => {
							const [k, d] = e.currentTarget.value.split(':');
							sortKey = k;
							sortDir = d as SortDir;
						}}
					>
						<option value="verdict:asc">Flagged first</option>
						<option value="tps:desc">Fastest (TPS)</option>
						<option value="ttft:asc">Lowest TTFT</option>
						<option value="price:asc">Cheapest</option>
						<option value="provider:asc">Provider A–Z</option>
					</select>
				</label>
				<ul class="flex flex-col gap-2">
					{#each rows as plan (plan.id)}
						<li
							class="relative rounded-sm border border-border bg-panel p-4 shadow-sm hover:border-accent-interactive"
						>
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0">
									<a
										class="font-semibold text-primary after:absolute after:inset-0 after:content-['']"
										href={resolve(`/providers/${plan.provider.slug}/${plan.slug}/`)}>{plan.name}</a
									>
									<p class="text-xs text-muted">{plan.provider.name}</p>
								</div>
								<span class="font-mono text-sm tabular text-primary"
									>{fmtPrice(plan.pricePerMonth, plan.currency)}<span class="text-muted">/mo</span
									></span
								>
							</div>
							<p class="mt-2 truncate text-xs text-muted">
								{plan.models.map((m) => m.model.name).join(' · ') || DASH}
							</p>
							<div
								class="mt-3 grid grid-cols-[auto_1fr_auto] items-center gap-x-3 font-mono text-xs"
							>
								<span class="text-muted">TPS</span>
								<div class="flex items-center gap-2">
									<span class="tabular text-primary">{fmtNum(plan.medianTps, 1)}</span>
									<BarMini value={plan.medianTps} max={maxTps} />
								</div>
								<span class="tabular text-muted"
									>TTFT <span class="text-primary"
										>{plan.medianTtft === null ? DASH : `${fmtNum(plan.medianTtft, 2)} s`}</span
									></span
								>
							</div>
							<div class="mt-3 flex items-center gap-2">
								<StatusBadge kind="verdict" value={plan.integrity.verdict} />
								{#if plan.integrity.total}
									<span class="font-mono text-[11px] tabular text-muted">
										{plan.integrity.pass}/{plan.integrity.total} pass{#if plan.integrity.fail}
											· <span class="text-tertiary">{plan.integrity.fail} fail</span>{/if}
									</span>
								{/if}
							</div>
						</li>
					{:else}
						<li class="rounded-sm border border-border bg-panel p-6 text-center text-sm text-muted">
							No plans match these filters.
						</li>
					{/each}
				</ul>
			</div>
			<p class="font-mono text-[11px] text-muted">
				TPS = output tokens/s, TTFT = time to first token; {data.windowDays}-day means, median
				across a plan’s models. Integrity counts the latest result of each audit test per model.
			</p>
		</div>
	{/if}
</section>
