<script lang="ts">
	import Status from '#lib/components/Status.svelte';
	import {
		audits,
		auditsForPlan,
		catalog,
		fmtPrice,
		modelBySlug,
		planStatus,
		providerBySlug,
		usd,
		type EndpointInfo
	} from '#lib/data.ts';
	import { fmtEffect } from '#lib/labstats.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const plan = $derived(data.plan);
	const provider = $derived(providerBySlug.get(plan.provider));
	const rows = $derived(auditsForPlan(plan.slug));
	const history = $derived(audits.filter((a) => a.plan === plan.slug));

	const riskLabel = { high: 'High', medium: 'Medium', low: 'Low', unknown: 'Unknown' } as const;
	const confidenceLabel = {
		official: 'from the provider’s own pages',
		mixed: 'partly from third-party trackers',
		'third-party': 'from third-party trackers only'
	} as const;
	const fmtP = (p?: number) => (p == null ? '—' : p < 0.001 ? '< 0.001' : p.toFixed(3));
	const host = (url: string) => url.replace(/^https?:\/\//, '');
	const yesNo = (v: boolean) => (v ? 'yes' : 'no');
	const endpointFacts = (e: EndpointInfo) => [
		['Endpoint', host(e.base_url)],
		['Model id', e.api_model],
		['Returns logprobs', yesNo(e.logprobs)],
		['Reasoning can be switched off', e.thinking_off ? 'yes' : 'no / undocumented'],
		['Checked by a live call', yesNo(e.verified)]
	];
</script>

<svelte:head>
	<title>{plan.name} — {site.name}</title>
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pt-12 sm:px-6">
	<nav class="text-sm text-ink-2" aria-label="Breadcrumb">
		<a class="hover:text-ink" href={resolve('/plans')}>Plans</a>
		<span class="mx-1.5 text-muted">/</span>
		<span>{provider?.name}</span>
	</nav>

	<div class="mt-4 flex flex-wrap items-start justify-between gap-4">
		<div>
			<h1 class="text-3xl font-semibold sm:text-4xl">{plan.name}</h1>
			<p class="mt-2 text-ink-2">
				{provider?.name} ·
				{plan.kind === 'maker'
					? `sold by the maker of ${plan.models.map((m) => modelBySlug.get(m)?.name).join(', ')}`
					: 'reseller of other makers’ models'}
			</p>
		</div>
		<Status kind={planStatus(plan.slug)} />
	</div>

	{#if plan.availability}
		<p class="mt-5 rounded-md border border-warn/40 bg-warn-wash px-4 py-2.5 text-sm text-warn-ink">
			{plan.availability}
		</p>
	{/if}

	<div class="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
		<section class="card overflow-hidden">
			<h2 class="border-b border-line px-5 py-3 text-sm font-medium">Tiers</h2>
			<table class="w-full text-sm">
				<tbody>
					{#each plan.tiers as t (t.name)}
						<tr class="border-b border-line last:border-0">
							<td class="px-5 py-2.5 font-medium">{t.name}</td>
							<td class="num px-5 py-2.5 whitespace-nowrap">
								{fmtPrice(t.price, t.currency)}
								{#if t.currency !== 'USD'}<span class="text-xs text-muted"
										>≈ ${Math.round(usd(t.price, t.currency))}</span
									>{/if}
							</td>
							<td class="px-5 py-2.5 text-ink-2">{t.limits}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="border-t border-line px-5 py-3 text-xs text-ink-2">
				<span class="text-muted">How usage is counted:</span>
				{plan.metering}
			</p>
		</section>

		<section class="card p-5">
			<h2 class="text-sm font-medium">Terms and automated testing</h2>
			<p class="mt-2 text-sm">
				<span class="font-medium">{riskLabel[plan.tos_risk]} risk.</span>
				<span class="text-ink-2">{plan.tos_note}</span>
			</p>
			<p class="mt-4 text-xs text-muted">
				Facts on this page are {confidenceLabel[plan.confidence]}, snapshot {catalog.snapshot}.
			</p>
			{#if plan.sources?.length}
				<ul class="mt-2 space-y-1 text-xs">
					{#each plan.sources as s (s)}
						<li><a class="link break-all" href={s} rel="external">{host(s)}</a></li>
					{/each}
				</ul>
			{/if}
		</section>
	</div>

	{#if plan.notes?.length || plan.reports?.length}
		<section class="mt-10">
			<h2 class="text-xl font-semibold">Worth knowing</h2>
			<ul class="mt-4 space-y-2.5 text-sm text-ink-2">
				{#each plan.notes ?? [] as n (n)}
					<li class="flex gap-2.5">
						<span class="mt-2 size-1.5 shrink-0 rounded-full bg-muted"></span><span>{n}</span>
					</li>
				{/each}
				{#each plan.reports ?? [] as r (r.url)}
					<li class="flex gap-2.5">
						<span class="mt-2 size-1.5 shrink-0 rounded-full bg-warn"></span>
						<span>
							<span class="font-medium text-ink">Community report, {r.date}:</span>
							{r.text} <a class="link" href={r.url} rel="external">Source</a>
						</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	<section class="mt-12">
		<h2 class="text-xl font-semibold">What gets compared</h2>
		<p class="mt-1 max-w-3xl text-sm text-ink-2">
			For each model, the plan’s endpoint is held against the model maker’s own pay-per-token API
			with identical requests, sampled side by side. Which probes can run depends on what both
			endpoints expose.
		</p>

		<div class="mt-6 space-y-6">
			{#each rows as a (a.target.slug)}
				{@const latest = a.latest}
				{@const model = modelBySlug.get(a.target.model ?? '')}
				<article class="card overflow-hidden">
					<header
						class="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4"
					>
						<div>
							<h3 class="font-medium">{model?.name ?? a.target.model}</h3>
							<p class="text-xs text-ink-2">
								{model?.open_weights ? 'Open weights' : 'Closed weights'}{model?.notes
									? ` · ${model.notes}`
									: ''}
							</p>
						</div>
						<Status kind={latest ? latest.status : 'untested'} />
					</header>

					<div class="grid gap-px bg-line sm:grid-cols-2">
						{#each [['This plan', a.target], ['Official API (reference)', a.reference]] as [label, e] (label)}
							{@const ep = e as EndpointInfo}
							<dl class="bg-surface px-5 py-4 text-sm">
								<dt class="mb-2 text-xs font-medium text-muted">{label}</dt>
								{#each endpointFacts(ep) as [k, v] (k)}
									<div class="flex justify-between gap-4 py-0.5">
										<dd class="text-ink-2">{k}</dd>
										<dd class="num text-right text-xs break-all">{v}</dd>
									</div>
								{/each}
								{#if ep.notes}<p class="mt-2 text-xs text-warn-ink">{ep.notes}</p>{/if}
							</dl>
						{/each}
					</div>

					<div class="border-t border-line px-5 py-4">
						<h4 class="text-xs font-medium text-muted">Probes</h4>
						<ul class="mt-2 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
							{#each Object.entries(a.probes) as [p, reason] (p)}
								{@const v = latest?.verdicts.find((x) => x.probe === p)}
								<li class="flex gap-2.5">
									{#if reason}
										<svg
											viewBox="0 0 16 16"
											class="mt-0.5 size-4 shrink-0 text-muted"
											fill="none"
											stroke="currentColor"
											stroke-width="1.6"
											aria-label="cannot run"
											><circle cx="8" cy="8" r="6" /><path d="m4 12 8-8" /></svg
										>
									{:else}
										<svg
											viewBox="0 0 16 16"
											class="mt-0.5 size-4 shrink-0 text-good-ink"
											fill="none"
											stroke="currentColor"
											stroke-width="1.8"
											aria-label="can run"
											><path
												d="m3.5 8.5 3 3 6-7"
												stroke-linecap="round"
												stroke-linejoin="round"
											/></svg
										>
									{/if}
									<div class="min-w-0">
										<span class={reason ? 'text-ink-2' : 'text-ink'}
											>{catalog.probes[p]?.title ?? p}</span
										>
										<span class="text-xs text-muted"> · {catalog.probes[p]?.detects}</span>
										{#if reason}
											<div class="text-xs text-muted">Not possible: {reason}</div>
										{:else if v && !v.skipped && !v.inconclusive}
											<div class="text-xs {v.flagged ? 'text-bad-ink' : 'text-good-ink'}">
												{v.flagged ? 'Gap' : 'Pass'}: {fmtEffect(
													v.effect ?? 0,
													v.effect_name ?? ''
												)}, q = {fmtP(v.q_value ?? v.p_value)}
											</div>
										{/if}
									</div>
								</li>
							{/each}
						</ul>
					</div>

					{#if !latest}
						<footer class="border-t border-line bg-sunken/40 px-5 py-3 text-xs text-ink-2">
							Not audited yet: needs a paid account on this plan and pay-per-token access to
							<span class="num">{a.reference.slug}</span>. Command:
							<code class="inline"
								>planaudit audit --target {a.target.slug} --tier standard --calibrate</code
							>
						</footer>
					{:else}
						<footer class="border-t border-line px-5 py-3 text-xs text-muted">
							{latest.tier} tier · {latest.started_at.slice(0, 10)} ·
							<a class="link" href={resolve('/data')}>raw result</a>
						</footer>
					{/if}
				</article>
			{/each}
		</div>
	</section>

	{#if history.length > 1}
		<section class="mt-12">
			<h2 class="text-xl font-semibold">History</h2>
			<ul class="mt-4 divide-y divide-line text-sm">
				{#each history as h (h.started_at + h.target.slug)}
					<li class="flex items-center justify-between py-2">
						<span class="num text-ink-2"
							>{h.started_at.slice(0, 16).replace('T', ' ')} · {h.target.slug} · {h.tier}</span
						>
						<Status kind={h.status} />
					</li>
				{/each}
			</ul>
		</section>
	{/if}
</div>
