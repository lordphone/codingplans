<script lang="ts">
	import Status from '#lib/components/Status.svelte';
	import { auditsForPlan, audits, modelBySlug, planStatus, providerBySlug } from '#lib/data.ts';
	import { fmtEffect } from '#lib/labstats.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const plan = $derived(data.plan);
	const provider = $derived(providerBySlug.get(plan.provider));
	const rows = $derived(auditsForPlan(plan.slug));
	const history = $derived(audits.filter((a) => a.plan === plan.slug));

	const fmtP = (p?: number) => (p == null ? '—' : p < 0.001 ? '< 0.001' : p.toFixed(3));
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
				{provider?.name} · <span class="num">{plan.price} {plan.currency}</span> per month
			</p>
		</div>
		<Status kind={planStatus(plan.slug)} />
	</div>

	<dl class="card mt-8 grid gap-px overflow-hidden bg-line sm:grid-cols-3">
		<div class="bg-surface p-5">
			<dt class="text-xs text-muted">Advertised limits</dt>
			<dd class="mt-1 text-sm">{plan.limits}</dd>
		</div>
		<div class="bg-surface p-5">
			<dt class="text-xs text-muted">Models</dt>
			<dd class="mt-1 text-sm">
				{plan.models.map((m) => modelBySlug.get(m)?.name ?? m).join(', ')}
			</dd>
		</div>
		<div class="bg-surface p-5">
			<dt class="text-xs text-muted">Terms of service and automated testing</dt>
			<dd class="mt-1 text-sm">
				<span class="font-medium capitalize">{plan.tos_risk} risk.</span>
				{plan.tos_note}
			</dd>
		</div>
	</dl>

	<h2 class="mt-14 text-xl font-semibold">Audits</h2>
	<p class="mt-1 text-sm text-ink-2">
		One comparison per model the plan serves: the plan endpoint against the model maker’s official
		API, sampled side by side in the same time window.
	</p>

	<div class="mt-6 space-y-6">
		{#each rows as a (a.target.slug)}
			{@const latest = a.latest}
			<section class="card">
				<header
					class="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4"
				>
					<div>
						<h3 class="font-medium">
							{modelBySlug.get(a.target.model ?? '')?.name ?? a.target.model}
						</h3>
						<p class="num mt-0.5 text-xs text-muted">
							{a.target.base_url} <span class="text-ink-2">vs</span>
							{a.reference.base_url}
						</p>
					</div>
					<Status kind={latest ? latest.status : 'untested'} />
				</header>
				{#if latest}
					<div class="overflow-x-auto">
						<table class="w-full min-w-[620px] text-left text-sm">
							<thead class="text-xs text-muted">
								<tr class="border-b border-line">
									<th class="px-5 py-2.5 font-medium">Probe</th>
									<th class="px-5 py-2.5 font-medium">Looks for</th>
									<th class="px-5 py-2.5 text-right font-medium">Effect</th>
									<th class="px-5 py-2.5 text-right font-medium">Margin</th>
									<th class="px-5 py-2.5 text-right font-medium">q-value</th>
									<th class="px-5 py-2.5 font-medium">Verdict</th>
								</tr>
							</thead>
							<tbody>
								{#each latest.verdicts as v (v.probe)}
									<tr class="border-b border-line last:border-0">
										<td class="px-5 py-2.5 font-medium">{v.title ?? v.probe}</td>
										<td class="px-5 py-2.5 text-ink-2">{v.detects ?? ''}</td>
										{#if v.skipped || v.inconclusive}
											<td colspan="3" class="px-5 py-2.5 text-right text-ink-2"
												>{v.skipped ?? v.inconclusive}</td
											>
											<td class="px-5 py-2.5"
												><Status
													kind="inconclusive"
													label={v.skipped ? 'Skipped' : 'Inconclusive'}
												/></td
											>
										{:else}
											<td class="num px-5 py-2.5 text-right"
												>{fmtEffect(v.effect ?? 0, v.effect_name ?? '')}</td
											>
											<td class="num px-5 py-2.5 text-right text-ink-2"
												>{v.margin == null ? '—' : fmtEffect(v.margin, v.effect_name ?? '')}</td
											>
											<td class="num px-5 py-2.5 text-right">{fmtP(v.q_value ?? v.p_value)}</td>
											<td class="px-5 py-2.5"
												><Status
													kind={v.flagged ? 'gap' : 'pass'}
													label={v.flagged ? 'Gap' : 'Pass'}
												/></td
											>
										{/if}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="px-5 py-3 text-xs text-muted">
						{latest.tier} tier · {latest.started_at.slice(0, 10)} ·
						<a class="link" href={resolve('/data')}>raw result</a>
					</p>
				{:else}
					<div class="px-5 py-6 text-sm text-ink-2">
						<p>
							Not audited yet. Running it needs an account on this plan and pay-per-token access to <span
								class="num text-ink">{a.reference.slug}</span
							>; the command is
						</p>
						<pre
							class="num mt-3 overflow-x-auto rounded-md bg-sunken px-3 py-2 text-xs text-ink">planaudit audit --target {a
								.target.slug} --tier standard</pre>
					</div>
				{/if}
			</section>
		{/each}
	</div>

	{#if history.length > 1}
		<h2 class="mt-14 text-xl font-semibold">History</h2>
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
	{/if}
</div>
