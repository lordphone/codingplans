<script lang="ts">
	import Status from '#lib/components/Status.svelte';
	import { catalog, lab, modelBySlug, planStatus, providerBySlug } from '#lib/data.ts';
	import { summary } from '#lib/labstats.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	const ref = lab[0];
	const s = ref ? summary(ref) : null;
	const statusOrder = { gap: 0, inconclusive: 1, match: 2, untested: 3 } as const;
	const plans = [...catalog.plans].sort(
		(a, b) => statusOrder[planStatus(a.slug)] - statusOrder[planStatus(b.slug)]
	);
	const audited = catalog.plans.filter((p) => planStatus(p.slug) !== 'untested').length;

	const threats = [
		{
			name: 'Quantized weights',
			body: 'Serving INT4/FP8 weights instead of the published precision. Shifts next-token probabilities and breaks exact multi-step arithmetic first.',
			probes: 'logprob · distribution · arithmetic'
		},
		{
			name: 'Model swap',
			body: 'A smaller sibling answering under the flagship’s name. Different answers, different accuracy, sometimes a different tokenizer.',
			probes: 'distribution · code · accounting'
		},
		{
			name: 'Truncated context',
			body: 'Long prompts silently cut down to a cheaper window. Facts from the cut part become unrecoverable.',
			probes: 'needle'
		},
		{
			name: 'Phantom caching',
			body: 'Usage reports cached tokens that were never cached, or the discount is applied without the speed-up.',
			probes: 'cache'
		},
		{
			name: 'Hidden prompts',
			body: 'An injected system prompt that costs you context and changes behaviour. Shows up as extra prompt tokens.',
			probes: 'accounting'
		},
		{
			name: 'Throttling',
			body: 'Slower streams on the plan than on the paid API, especially at peak hours.',
			probes: 'speed'
		}
	];
</script>

<svelte:head>
	<title>{site.name} — {site.tagline}</title>
</svelte:head>

<section class="border-b border-line">
	<div class="mx-auto max-w-6xl px-4 pt-16 pb-14 sm:px-6 sm:pt-24 sm:pb-20">
		<p class="eyebrow">{site.tagline}</p>
		<h1 class="mt-4 max-w-3xl text-4xl leading-[1.05] font-semibold sm:text-6xl">
			Same model, <span class="text-ink-2">different plan?</span>
		</h1>
		<p class="mt-6 max-w-2xl text-lg text-ink-2">
			Flat-rate coding plans promise the same models their makers sell by the token. We send
			identical requests to both, side by side, and measure the gap: quantized weights, swapped
			models, truncated context, caching that isn’t.
		</p>
		<div class="mt-8 flex flex-wrap gap-3">
			<a
				href={resolve('/plans')}
				class="rounded-md bg-ink px-4 py-2.5 text-sm font-medium text-page transition-opacity hover:opacity-85"
				>See the plans</a
			>
			<a
				href={resolve('/lab')}
				class="rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-medium transition-colors hover:bg-sunken"
				>How we validate the tests</a
			>
		</div>

		<dl class="mt-14 grid max-w-3xl grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
			<div>
				<dt class="text-sm text-ink-2">Plans tracked</dt>
				<dd class="num mt-1 text-3xl font-medium">{catalog.plans.length}</dd>
			</div>
			<div>
				<dt class="text-sm text-ink-2">Audited so far</dt>
				<dd class="num mt-1 text-3xl font-medium">{audited}</dd>
			</div>
			{#if s}
				<div>
					<dt class="text-sm text-ink-2">Lab corner-cuts caught</dt>
					<dd class="num mt-1 text-3xl font-medium">
						{s.detected}<span class="text-xl text-muted">/{s.cuts}</span>
					</dd>
				</div>
				<div>
					<dt class="text-sm text-ink-2">False alarms on honest setups</dt>
					<dd class="num mt-1 text-3xl font-medium">
						{s.falseAlarms}<span class="text-xl text-muted">/{s.honestChecks}</span>
					</dd>
				</div>
			{/if}
		</dl>
	</div>
</section>

<section class="mx-auto max-w-6xl px-4 pt-16 sm:px-6">
	<div class="flex flex-wrap items-end justify-between gap-4">
		<div>
			<h2 class="text-2xl font-semibold">Plans under audit</h2>
			<p class="mt-1 text-ink-2">
				Each plan is compared with the official API of the model it serves.
			</p>
		</div>
		<a class="link text-sm" href={resolve('/plans')}>All plan details →</a>
	</div>

	<div class="card mt-6 overflow-x-auto">
		<table class="w-full min-w-[640px] text-left text-sm">
			<thead class="text-xs text-muted">
				<tr class="border-b border-line">
					<th class="px-4 py-3 font-medium">Plan</th>
					<th class="px-4 py-3 font-medium">Models</th>
					<th class="px-4 py-3 text-right font-medium">Price / month</th>
					<th class="px-4 py-3 font-medium">Result</th>
				</tr>
			</thead>
			<tbody>
				{#each plans as p (p.slug)}
					<tr class="border-b border-line last:border-0 hover:bg-sunken/60">
						<td class="px-4 py-3">
							<a
								href={resolve('/plans/[slug]', { slug: p.slug })}
								class="font-medium hover:text-accent">{p.name}</a
							>
							<div class="text-xs text-ink-2">{providerBySlug.get(p.provider)?.name}</div>
						</td>
						<td class="px-4 py-3 text-ink-2">
							{p.models.map((m) => modelBySlug.get(m)?.name ?? m).join(', ')}
						</td>
						<td class="num px-4 py-3 text-right">{p.price} {p.currency}</td>
						<td class="px-4 py-3"><Status kind={planStatus(p.slug)} /></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if audited === 0}
		<p class="mt-3 text-sm text-ink-2">
			No plan has been audited yet: each audit needs paid access to both the plan and the official
			API. The detectors are validated first, in the <a class="link" href={resolve('/lab')}>lab</a>.
		</p>
	{/if}
</section>

<section class="mx-auto max-w-6xl px-4 pt-20 sm:px-6">
	<h2 class="text-2xl font-semibold">What we look for</h2>
	<p class="mt-1 max-w-2xl text-ink-2">
		Every corner a provider could cut, and the probe built to catch it.
	</p>
	<div
		class="mt-6 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-3"
	>
		{#each threats as t (t.name)}
			<div class="bg-surface p-5">
				<h3 class="font-medium">{t.name}</h3>
				<p class="mt-1.5 text-sm text-ink-2">{t.body}</p>
				<p class="num mt-3 text-xs text-muted">{t.probes}</p>
			</div>
		{/each}
	</div>
</section>

{#if ref && s}
	<section class="mx-auto max-w-6xl px-4 pt-20 sm:px-6">
		<div class="grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:items-center">
			<div>
				<p class="eyebrow">Calibration lab</p>
				<h2 class="mt-2 text-2xl font-semibold">Tests are tested before they’re trusted</h2>
				<p class="mt-3 text-ink-2">
					On our own GPU we serve {ref.name} in {ref.variants.length} configurations: an honest reference,
					{s.honest} legitimate variations of it, and {s.cuts} deliberate corner-cuts. A detector only
					counts as working if it flags the cuts and stays quiet on the honest variations, and we publish
					how many requests it needs.
				</p>
				<a class="link mt-4 inline-block text-sm" href={resolve('/lab')}
					>Explore the lab results →</a
				>
			</div>
			<div class="card p-5">
				<div class="flex items-baseline justify-between">
					<h3 class="font-medium">{ref.name}</h3>
					<span class="num text-xs text-muted">{ref.engine.gpu} · vLLM {ref.engine.vllm}</span>
				</div>
				<ul class="mt-4 space-y-2 text-sm">
					{#each ref.variants.filter((v) => v.kind === 'cut') as v (v.id)}
						{@const hit = ref.results.some((r) => r.variant === v.id && r.flagged)}
						<li class="flex items-center justify-between gap-3">
							<span class="text-ink-2">{v.label}</span>
							<Status kind={hit ? 'detected' : 'missed'} />
						</li>
					{/each}
				</ul>
			</div>
		</div>
	</section>
{/if}
