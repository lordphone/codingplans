<script lang="ts">
	import { resolve } from '$app/paths';
	import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ModelMetricsTable from '$lib/components/ModelMetricsTable.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import { fmtDate, fmtPrice } from '$lib/format';
	import { SITE } from '$lib/site';

	let { data } = $props();
	const provider = $derived(data.provider);
	const maxTps = $derived(
		Math.max(1, ...provider.plans.flatMap((p) => p.models.map((m) => m.perf.tps ?? 0)))
	);
</script>

<svelte:head>
	<title>{provider.name} · {SITE.name}</title>
	<meta
		name="description"
		content="{provider.name} coding plans: speed and integrity audits against the official API."
	/>
</svelte:head>

<Breadcrumbs items={[{ label: 'Directory', href: resolve('/') }, { label: provider.name }]} />

<PageHeader eyebrow="Provider" title={provider.name} variant="entity">
	{#if provider.description}<p>{provider.description}</p>{/if}
	{#snippet aside()}
		<dl class="grid grid-cols-2 gap-x-8 gap-y-1 font-mono text-xs">
			<dt class="text-muted">Active plans</dt>
			<dd class="text-right text-primary">{provider.plans.length}</dd>
			{#if provider.websiteUrl}
				<dt class="text-muted">Website</dt>
				<dd class="text-right">
					<a class="link" href={provider.websiteUrl} rel="noopener noreferrer" target="_blank"
						>{new URL(provider.websiteUrl).hostname} ↗</a
					>
				</dd>
			{/if}
		</dl>
	{/snippet}
</PageHeader>

<div class="mt-10 flex flex-col gap-12">
	{#each provider.plans as plan (plan.id)}
		{@const href = resolve(`/providers/${provider.slug}/${plan.slug}/`)}
		<section aria-labelledby="plan-{plan.slug}">
			<div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
				<div class="min-w-0">
					<h2 id="plan-{plan.slug}" class="text-xl font-semibold tracking-tight text-primary">
						<a {href} class="hover:text-accent-interactive">{plan.name}</a>
					</h2>
					<p class="mt-1 flex flex-wrap gap-x-3 font-mono text-xs text-muted">
						<span class="text-primary">{fmtPrice(plan.pricePerMonth, plan.currency)}/mo</span>
						{#if plan.advertisedLimits}<span>{plan.advertisedLimits}</span>{/if}
						<span>Last measured {fmtDate(plan.lastMeasuredAt)}</span>
					</p>
				</div>
				<div class="flex items-center gap-3">
					<StatusBadge kind="verdict" value={plan.integrity.verdict} size="md" />
					<a {href} class="link font-mono text-xs whitespace-nowrap">Plan detail →</a>
				</div>
			</div>
			{#if plan.models.length}
				<ModelMetricsTable models={plan.models} caption="Models in {plan.name}" {maxTps} />
			{:else}
				<EmptyState title="No models listed for this plan yet" />
			{/if}
		</section>
	{:else}
		<EmptyState title="No active plans">
			<p>This provider has no active plans in the directory.</p>
		</EmptyState>
	{/each}
</div>
