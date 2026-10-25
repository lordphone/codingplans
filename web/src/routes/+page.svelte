<script lang="ts">
	import Status from '#lib/components/Status.svelte';
	import {
		catalog,
		coverage,
		fmtPrice,
		lab,
		modelBySlug,
		planStatus,
		providerBySlug
	} from '#lib/data.ts';
	import { fmtRequests, result, summary } from '#lib/labstats.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	const ref = lab[0];
	const s = ref ? summary(ref) : null;
	const audited = catalog.plans.filter((p) => planStatus(p.slug) !== 'untested').length;

	// Detection cost of the same corner-cut (INT4 weights) across model sizes,
	// with and without logprobs: the project's central measurement.
	const sizes = [...lab].sort((a, b) => a.params_b - b.params_b);
	const sweep = sizes.map((f) => ({
		size: f.params_b,
		logprob: result(f, 'int4-awq', 'logprob')?.requests_for_95 ?? null,
		text: result(f, 'int4-awq', 'distribution')?.requests_for_95 ?? null
	}));
	const maxReq = Math.max(...sweep.flatMap((r) => [r.logprob ?? 0, r.text ?? 0]), 10);
	const ratios = sweep
		.filter((r) => r.logprob && r.text)
		.map((r) => Math.round(r.text! / r.logprob!));
	const largestHardest = ratios.length > 1 && ratios.at(-1) === Math.max(...ratios);
	const ratio = ratios.length ? [Math.min(...ratios), Math.max(...ratios)] : null;
	const w = (n: number | null) => (n == null ? 0 : (Math.log10(n) / Math.log10(maxReq)) * 100);

	const steps = [
		{
			title: 'Same requests, same moment',
			body: 'Each plan and the official pay-per-token API of the same model get an identical panel of requests, interleaved in one schedule so time-of-day load hits both.'
		},
		{
			title: 'Eight probes measure the gap',
			body: 'Next-token probabilities, answer distributions, arithmetic, coding tasks, long-context recall, caching, token counts and speed: each catches a different corner-cut.'
		},
		{
			title: 'Only flag what honesty can’t explain',
			body: 'Two honest servers never match bit for bit. A gap is reported only when it is significant and bigger than anything legitimate serving differences produced in our lab.'
		}
	];

	const milestones = [
		{ label: 'Detection method', state: 'done', note: 'Eight probes, open source' },
		{
			label: 'Validated in the lab',
			state: ref ? 'done' : 'next',
			note: s ? `${s.detected}/${s.cuts} corner-cuts caught, ${s.falseAlarms} false alarms` : ''
		},
		{
			label: 'First plan audits',
			state: audited ? 'done' : 'next',
			note: audited ? `${audited} audited` : 'Needs paid accounts on both sides'
		},
		{ label: 'Paper and dataset', state: 'later', note: 'Workshop paper, public data' }
	] as const;

	const featured = [...catalog.plans].sort(
		(a, b) => coverage(b.slug).runnable - coverage(a.slug).runnable
	);
</script>

<svelte:head>
	<title>{site.name} — {site.tagline}</title>
</svelte:head>

<section class="border-b border-line">
	<div class="mx-auto max-w-6xl px-4 pt-16 pb-14 sm:px-6 sm:pt-24 sm:pb-16">
		<p class="eyebrow">{site.tagline}</p>
		<h1 class="mt-4 max-w-3xl text-4xl leading-[1.05] font-semibold sm:text-6xl">
			Same model, <span class="text-ink-2">different plan?</span>
		</h1>
		<p class="mt-6 max-w-2xl text-lg text-ink-2">
			Flat-rate coding plans promise the same models their makers sell by the token, for a fraction
			of the price. We check whether you get the same thing: the same weights at full precision, the
			full context, real caching, no hidden prompts.
		</p>
		<div class="mt-8 flex flex-wrap gap-3">
			<a
				href={resolve('/plans')}
				class="rounded-md bg-ink px-4 py-2.5 text-sm font-medium text-page transition-opacity hover:opacity-85"
				>Compare {catalog.plans.length} plans</a
			>
			<a
				href={resolve('/lab')}
				class="rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-medium transition-colors hover:bg-sunken"
				>How we know the tests work</a
			>
		</div>

		<ol
			class="mt-14 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4"
			aria-label="Project status"
		>
			{#each milestones as m, i (m.label)}
				<li class="bg-surface p-4">
					<div class="flex items-center gap-2 text-xs">
						{#if m.state === 'done'}
							<span class="flex size-4 items-center justify-center rounded-full bg-good text-white">
								<svg
									viewBox="0 0 16 16"
									class="size-3"
									fill="none"
									stroke="currentColor"
									stroke-width="2.2"
									aria-hidden="true"
									><path d="m3.5 8.5 3 3 6-7" stroke-linecap="round" stroke-linejoin="round" /></svg
								>
							</span>
							<span class="font-medium text-good-ink">Done</span>
						{:else if m.state === 'next'}
							<span class="size-4 rounded-full border-2 border-accent"></span>
							<span class="font-medium text-accent">Next</span>
						{:else}
							<span class="size-4 rounded-full border-2 border-grid"></span>
							<span class="text-muted">Later</span>
						{/if}
						<span class="num ml-auto text-muted">{i + 1}</span>
					</div>
					<div class="mt-2 font-medium">{m.label}</div>
					<div class="mt-0.5 text-sm text-ink-2">{m.note}</div>
				</li>
			{/each}
		</ol>
	</div>
</section>

<section class="mx-auto max-w-6xl px-4 pt-16 sm:px-6">
	<h2 class="text-2xl font-semibold">How an audit works</h2>
	<div class="mt-6 grid gap-6 md:grid-cols-3">
		{#each steps as st, i (st.title)}
			<div>
				<div class="num text-sm text-muted">0{i + 1}</div>
				<h3 class="mt-1 font-medium">{st.title}</h3>
				<p class="mt-1.5 text-sm text-ink-2">{st.body}</p>
			</div>
		{/each}
	</div>
</section>

{#if ref && s}
	<section class="mx-auto max-w-6xl px-4 pt-20 sm:px-6">
		<div class="grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:items-start">
			<div>
				<p class="eyebrow">From the calibration lab</p>
				<h2 class="mt-2 text-2xl font-semibold">
					We cut the corners ourselves, then tried to catch them
				</h2>
				<p class="mt-3 text-ink-2">
					On our own GPU we served {ref.name} in {ref.variants.length} configurations: an honest reference,
					{s.honest} legitimate variations of it, and {s.cuts} deliberate corner-cuts, from quantized
					weights to faked caching. The probes caught {s.detected} of the {s.cuts} cuts and raised
					{s.falseAlarms === 0 ? 'no false alarm' : `${s.falseAlarms} false alarms`} on the honest setups.
				</p>
				{#if s.missed.length}
					<p class="mt-3 text-sm text-ink-2">Not caught: {s.missed.join(', ')}.</p>
				{/if}
				<a class="link mt-4 inline-block text-sm" href={resolve('/lab')}>See every result →</a>
			</div>

			{#if sweep.length > 1}
				<figure class="card p-5">
					<figcaption>
						<div class="font-medium">Requests needed to catch INT4 weights</div>
						<div class="mt-0.5 text-sm text-ink-2">
							95% detection, by model size.
							{#if ratio}Without logprobs the same cut takes {ratio[0]}–{ratio[1]}× more requests{largestHardest
									? ', most at the largest size'
									: ''}.{/if}
						</div>
					</figcaption>
					<div class="mt-5 space-y-4">
						{#each sweep as r (r.size)}
							<div>
								<div class="num mb-1.5 text-xs text-muted">{r.size}B parameters</div>
								{#each [['With logprobs', r.logprob, 'bg-s1'], ['Text only', r.text, 'bg-s2']] as [label, n, cls] (label)}
									<div class="flex items-center gap-3 py-0.5 text-sm">
										<span class="w-24 shrink-0 text-ink-2">{label}</span>
										<span class="relative h-4 flex-1">
											{#if n != null}
												<span
													class="absolute inset-y-0 left-0 rounded-r {cls}"
													style:width="{Math.max(2, w(n as number))}%"
												></span>
											{/if}
										</span>
										<span class="num w-12 shrink-0 text-right"
											>{n == null ? 'missed' : fmtRequests(n as number)}</span
										>
									</div>
								{/each}
							</div>
						{/each}
					</div>
					<p class="mt-4 text-xs text-muted">
						Log scale. Requests counted on both endpoints. {ref.engine.gpu}, vLLM {ref.engine.vllm}.
					</p>
				</figure>
			{/if}
		</div>
	</section>
{/if}

<section class="mx-auto max-w-6xl px-4 pt-20 sm:px-6">
	<div class="flex flex-wrap items-end justify-between gap-4">
		<div>
			<h2 class="text-2xl font-semibold">The plans</h2>
			<p class="mt-1 text-ink-2">
				{audited === 0
					? 'None audited yet. Each needs paid access to the plan and to the official API.'
					: `${audited} of ${catalog.plans.length} audited.`}
			</p>
		</div>
		<a class="link text-sm" href={resolve('/plans')}>Compare all →</a>
	</div>
	<div class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
		{#each featured as p (p.slug)}
			{@const cov = coverage(p.slug)}
			{@const lo = [...p.tiers].sort((a, b) => a.price - b.price)[0]}
			<a
				href={resolve('/plans/[slug]', { slug: p.slug })}
				class="card group flex flex-col p-4 transition-colors hover:border-ink/25"
			>
				<div class="flex items-start justify-between gap-2">
					<div>
						<div class="font-medium group-hover:text-accent">{p.name}</div>
						<div class="text-xs text-ink-2">{providerBySlug.get(p.provider)?.name}</div>
					</div>
					<span class="num text-sm whitespace-nowrap">from {fmtPrice(lo.price, lo.currency)}</span>
				</div>
				<div class="mt-2 text-sm text-ink-2">
					{p.models.map((m) => modelBySlug.get(m)?.name ?? m).join(', ')}
				</div>
				<div class="mt-auto flex items-center justify-between pt-3 text-xs text-muted">
					<span>{cov.runnable} of {cov.total} probes apply</span>
					<Status kind={planStatus(p.slug)} />
				</div>
			</a>
		{/each}
	</div>
</section>

<section class="mx-auto max-w-6xl px-4 pt-20 sm:px-6">
	<h2 class="text-2xl font-semibold">Ground rules</h2>
	<div
		class="mt-6 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-4"
	>
		{#each [['Differences, not accusations', 'We report what we measured and how sure we are. A gap can have honest causes, and plans may disclose limits.'], ['Paying customers only', 'Audit accounts are bought like anyone else’s. No free credits from providers, who could recognise those accounts.'], ['Everything is open', 'The code, the lab configurations and every result are public, so anyone can rerun or challenge them.'], ['Right of reply', 'Providers can contest a result; replies and corrections are published next to it.']] as [t, b] (t)}
			<div class="bg-surface p-5">
				<h3 class="font-medium">{t}</h3>
				<p class="mt-1.5 text-sm text-ink-2">{b}</p>
			</div>
		{/each}
	</div>
	<a class="link mt-4 inline-block text-sm" href={resolve('/about')}>About the project →</a>
</section>
