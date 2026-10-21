<script lang="ts">
	import { resolve } from '$app/paths';
	import AuditTable from '$lib/components/AuditTable.svelte';
	import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import LineChart from '$lib/components/LineChart.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import { DASH, fmtDate, fmtNum, fmtPrice } from '$lib/format';
	import { SITE } from '$lib/site';

	let { data } = $props();
	const plan = $derived(data.plan);
	const provider = $derived(data.provider);
</script>

<svelte:head>
	<title>{plan.name} · {provider.name} · {SITE.name}</title>
	<meta
		name="description"
		content="{provider.name} {plan.name}: {data.windowDays}-day throughput, latency and integrity audit results versus the official API."
	/>
</svelte:head>

<Breadcrumbs
	items={[
		{ label: 'Directory', href: resolve('/') },
		{ label: provider.name, href: resolve(`/providers/${provider.slug}/`) },
		{ label: plan.name }
	]}
/>

<PageHeader eyebrow={provider.name} title={plan.name} variant="entity">
	{#if plan.description}<p>{plan.description}</p>{/if}
	{#snippet aside()}
		<div class="flex flex-col items-start gap-4 md:items-end">
			<StatusBadge kind="verdict" value={plan.integrity.verdict} size="md" />
			<dl class="grid grid-cols-[auto_auto] gap-x-6 gap-y-1 font-mono text-xs">
				<dt class="text-muted">Price</dt>
				<dd class="text-right text-primary">{fmtPrice(plan.pricePerMonth, plan.currency)}/mo</dd>
				<dt class="text-muted">Advertised</dt>
				<dd class="max-w-56 text-right text-primary">{plan.advertisedLimits ?? 'Not published'}</dd>
				<dt class="text-muted">Last measured</dt>
				<dd class="text-right text-primary">{fmtDate(plan.lastMeasuredAt)}</dd>
				{#if plan.url}
					<dt class="text-muted">Plan page</dt>
					<dd class="text-right">
						<a class="link" href={plan.url} rel="noopener noreferrer" target="_blank"
							>{new URL(plan.url).hostname} ↗</a
						>
					</dd>
				{/if}
			</dl>
		</div>
	{/snippet}
</PageHeader>

<dl
	class="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border lg:grid-cols-4"
>
	<StatTile
		label="Median TPS · {data.windowDays}d"
		value={fmtNum(plan.medianTps, 1)}
		hint="output tokens / s"
	/>
	<StatTile
		label="Median TTFT · {data.windowDays}d"
		value={plan.medianTtft === null ? DASH : `${fmtNum(plan.medianTtft, 2)}s`}
		hint="time to first token"
	/>
	<StatTile
		label="Tests passed"
		value={plan.integrity.total ? `${plan.integrity.pass}/${plan.integrity.total}` : DASH}
		hint="{plan.integrity.inconclusive + plan.integrity.error} inconclusive or errored"
		tone={plan.integrity.verdict === 'verified' ? 'positive' : 'default'}
	/>
	<StatTile
		label="Failures"
		value={String(plan.integrity.fail)}
		hint="after BH correction"
		tone={plan.integrity.fail ? 'negative' : 'default'}
	/>
</dl>

{#if plan.models.length > 1}
	<nav aria-label="Models in this plan" class="mt-8 flex flex-wrap items-center gap-2">
		<span class="mr-1 text-eyebrow text-muted">Jump to</span>
		{#each plan.models as m (m.model.id)}
			<a
				href="#model-{m.model.slug}"
				class="rounded-sm border border-border-strong bg-panel px-2.5 py-1.5 font-mono text-[11px] text-on-surface hover:border-accent-interactive hover:text-primary"
				>{m.model.name}</a
			>
		{/each}
	</nav>
{/if}

<div class="mt-10 flex flex-col gap-16">
	{#each plan.models as m (m.model.id)}
		{@const ref = m.audits.find((a) => a.referenceLabel)}
		<section id="model-{m.model.slug}" aria-labelledby="h-{m.model.slug}" class="scroll-mt-28">
			<div
				class="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between"
			>
				<div>
					<p class="text-eyebrow text-muted">Model</p>
					<h2 id="h-{m.model.slug}" class="mt-1 text-2xl font-semibold tracking-tight text-primary">
						{m.model.name}
					</h2>
					<p class="mt-1 font-mono text-xs text-muted">
						{m.model.slug} · usage limit: {m.usageLimit ?? 'not published'}
					</p>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<StatusBadge kind="quant" value={m.quant} size="md" />
					<StatusBadge kind="verdict" value={m.integrity.verdict} size="md" />
				</div>
			</div>

			<h3 class="mt-8 mb-4 text-nav text-primary">Speed · last {data.windowDays} days</h3>
			{#if m.series.length}
				<div class="grid gap-6 lg:grid-cols-2">
					<div class="rounded-sm border border-border bg-panel p-4 shadow-sm">
						<LineChart
							label="Throughput"
							unit="tok/s"
							color="throughput"
							points={m.series.map((p) => ({ day: p.day, value: p.tps, runs: p.runs }))}
						/>
					</div>
					<div class="rounded-sm border border-border bg-panel p-4 shadow-sm">
						<LineChart
							label="Time to first token"
							unit="s"
							color="latency"
							digits={2}
							points={m.series.map((p) => ({ day: p.day, value: p.ttft, runs: p.runs }))}
						/>
					</div>
				</div>
				<p class="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-muted">
					<span>{m.perf.runs} probe sessions</span>
					<span>TPS p10 {fmtNum(m.perf.tpsP10, 1)}</span>
					<span>TTFT p90 {m.perf.ttftP90 === null ? DASH : `${fmtNum(m.perf.ttftP90, 2)} s`}</span>
					<span
						>Error rate {m.perf.errorRate === null
							? DASH
							: `${fmtNum(m.perf.errorRate * 100, 1)}%`}</span
					>
					<span>Daily means, UTC</span>
				</p>
			{:else}
				<EmptyState title="No speed measurements in the last {data.windowDays} days" />
			{/if}

			<div class="mt-10 mb-4 flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
				<h3 class="text-nav text-primary">Integrity audit · latest result per test</h3>
				{#if ref}
					<p class="font-mono text-[11px] text-muted">
						Reference <span class="text-primary">{ref.referenceLabel}</span> vs plan
						<span class="text-primary">{ref.targetLabel}</span>
					</p>
				{/if}
			</div>
			{#if m.audits.length}
				<AuditTable audits={m.audits} caption="Audit results for {m.model.name} on {plan.name}" />
			{:else}
				<EmptyState title="No audit results yet">
					<p>This model has not been audited on this plan. Speed data above is unaffected.</p>
				</EmptyState>
			{/if}
		</section>
	{:else}
		<EmptyState title="No models listed for this plan yet" />
	{/each}
</div>

{#if data.siblings.length}
	<aside class="mt-16 border-t border-border pt-8" aria-labelledby="siblings">
		<h2 id="siblings" class="text-nav text-primary">Other {provider.name} plans</h2>
		<ul class="mt-4 flex flex-wrap gap-2">
			{#each data.siblings as s (s.slug)}
				<li>
					<a
						href={resolve(`/providers/${provider.slug}/${s.slug}/`)}
						class="inline-flex items-center gap-3 rounded-sm border border-border bg-panel px-3 py-2 text-sm hover:border-accent-interactive"
					>
						<span class="font-medium text-primary">{s.name}</span>
						<span class="font-mono text-xs text-muted"
							>{fmtPrice(s.pricePerMonth, s.currency)}/mo</span
						>
					</a>
				</li>
			{/each}
		</ul>
	</aside>
{/if}
