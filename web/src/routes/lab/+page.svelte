<script lang="ts">
	import DetectionMatrix from '#lib/components/DetectionMatrix.svelte';
	import LineChart, { type Series } from '#lib/components/LineChart.svelte';
	import Status from '#lib/components/Status.svelte';
	import { lab } from '#lib/data.ts';
	import { fmtEffect, fmtRequests, result, summary } from '#lib/labstats.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	// Fixed probe order = fixed series color per probe, on every chart.
	const PROBES = [
		'logprob',
		'distribution',
		'arithmetic',
		'code',
		'needle',
		'cache',
		'accounting',
		'speed'
	];
	const color = (p: string) => `var(--s${PROBES.indexOf(p) + 1})`;

	let familyId = $state(lab[0]?.family ?? '');
	const family = $derived(lab.find((f) => f.family === familyId) ?? lab[0]);
	let selected = $state(lab[0]?.variants.find((v) => v.kind === 'cut')?.id ?? '');
	$effect(() => {
		if (family && !family.variants.some((v) => v.id === selected))
			selected = family.variants.find((v) => v.kind === 'cut')?.id ?? '';
	});
	const variant = $derived(family?.variants.find((v) => v.id === selected));
	const s = $derived(family ? summary(family) : null);
	let showTable = $state(false);

	const series = $derived.by((): Series[] => {
		if (!family || !variant) return [];
		return PROBES.filter((p) => p in family.probes)
			.map((p) => {
				const r = result(family, variant.id, p);
				return {
					id: p,
					label: family.probes[p].title,
					color: color(p),
					points: (r?.curve ?? []).map((c) => ({ x: c.requests, y: c.rate })),
					muted: !r || !r.flagged
				};
			})
			.filter((x) => x.points.length);
	});

	// Size sweep: the same corner-cut across model sizes, requests for 95% detection.
	const sweepCuts = ['int4-awq', 'fp8'];
	const sweepProbes = ['logprob', 'distribution', 'arithmetic', 'code'];
	const sweepFamilies = [...lab].sort((a, b) => a.params_b - b.params_b);
	const fmtP = (p: number) => (p < 0.001 ? '< 0.001' : p.toFixed(3));
</script>

<svelte:head>
	<title>Calibration lab — {site.name}</title>
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pt-14 sm:px-6">
	<p class="eyebrow">Calibration lab</p>
	<h1 class="mt-3 max-w-3xl text-3xl font-semibold sm:text-4xl">
		Do the detectors work? We cut the corners ourselves and checked.
	</h1>
	<div class="mt-4 max-w-3xl space-y-3 text-ink-2">
		<p>
			A provider’s flagship model will never fit on one GPU, but the <em>detection methods</em> can be
			tested on a small open model where the truth is known. We serve it once as an honest reference,
			then as legitimate variations of that deployment (restarts, FP16, other kernels), then as deliberate
			corner-cuts: quantized weights, quantized KV cache, a smaller model under the same name, disabled
			or faked caching, truncated context, hidden prompts, throttling.
		</p>
		<p>
			Each probe compares a setup with the reference. It flags only when the difference is
			significant <em>and</em> larger than its margin, which is set just above the largest difference
			any honest variation produced. Subsampling the panels shows how many requests each detection costs.
		</p>
	</div>

	{#if !family}
		<div class="card mt-10 p-8 text-ink-2">
			No lab results have been published yet. Run <code class="inline">planaudit lab run</code> and
			<code class="inline">planaudit lab analyze</code>.
		</div>
	{:else}
		<div class="mt-10 flex flex-wrap items-center gap-2" role="tablist" aria-label="Model">
			{#each lab as f (f.family)}
				<button
					type="button"
					role="tab"
					aria-selected={f.family === family.family}
					onclick={() => (familyId = f.family)}
					class="rounded-md border px-3 py-1.5 text-sm transition-colors {f.family === family.family
						? 'border-ink bg-ink text-page'
						: 'border-line bg-surface text-ink-2 hover:text-ink'}">{f.name}</button
				>
			{/each}
			<span class="num ml-auto text-xs text-muted"
				>{family.engine.gpu} · vLLM {family.engine.vllm} · analysed {family.generated_at.slice(
					0,
					10
				)}</span
			>
		</div>

		{#if s}
			<dl
				class="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4"
			>
				<div class="bg-surface p-4">
					<dt class="text-xs text-muted">Corner-cuts detected</dt>
					<dd class="num mt-1 text-2xl">
						{s.detected}<span class="text-base text-muted">/{s.cuts}</span>
					</dd>
				</div>
				<div class="bg-surface p-4">
					<dt class="text-xs text-muted">Honest variations</dt>
					<dd class="num mt-1 text-2xl">{s.honest}</dd>
				</div>
				<div class="bg-surface p-4">
					<dt class="text-xs text-muted">False alarms (probe × honest setup)</dt>
					<dd class="num mt-1 text-2xl">
						{s.falseAlarms}<span class="text-base text-muted">/{s.honestChecks}</span>
					</dd>
				</div>
				<div class="bg-surface p-4">
					<dt class="text-xs text-muted">Significance level</dt>
					<dd class="num mt-1 text-2xl">α = {family.alpha}</dd>
				</div>
			</dl>
		{/if}

		<h2 class="mt-14 text-xl font-semibold">Detection matrix</h2>
		<p class="mt-1 mb-4 max-w-3xl text-sm text-ink-2">
			Every setup against the {family.variants.find((v) => v.id === family.reference)?.label} with every
			probe, on the full panel. A probe is only expected to catch the corners it targets; one strong detector
			per corner is enough.
		</p>
		<DetectionMatrix {family} bind:selected probeOrder={PROBES} />

		{#if variant}
			<section class="mt-14">
				<div class="flex flex-wrap items-end justify-between gap-3">
					<div>
						<p class="eyebrow">{variant.kind === 'cut' ? variant.cut : 'honest variation'}</p>
						<h2 class="mt-1 text-xl font-semibold">{variant.label}</h2>
						<p class="num mt-1 text-xs text-muted">
							{variant.model}
							{variant.args.join(' ')}
							{Object.keys(variant.proxy ?? {}).length
								? `· proxy ${JSON.stringify(variant.proxy)}`
								: ''}
						</p>
					</div>
					<button type="button" class="link text-sm" onclick={() => (showTable = !showTable)}
						>{showTable ? 'Show chart' : 'Show as table'}</button
					>
				</div>
				<div class="card mt-4 p-5">
					<h3 class="text-sm font-medium">
						{variant.kind === 'cut' ? 'Detection rate' : 'False-alarm rate'} vs. requests sent
					</h3>
					<p class="mb-3 text-xs text-ink-2">
						Share of random subsets of the panel on which the probe flags this setup. Faded lines:
						probes that do not flag it on the full panel.
					</p>
					{#if showTable}
						<div class="overflow-x-auto">
							<table class="w-full text-sm">
								<thead class="text-xs text-muted">
									<tr class="border-b border-line">
										<th class="py-2 text-left font-medium">Probe</th>
										<th class="py-2 text-right font-medium">Effect</th>
										<th class="py-2 text-right font-medium">Margin</th>
										<th class="py-2 text-right font-medium">p</th>
										<th class="py-2 text-right font-medium">Requests for 95%</th>
										<th class="py-2 pl-4 text-left font-medium">Full panel</th>
									</tr>
								</thead>
								<tbody>
									{#each PROBES.filter((p) => p in family.probes) as p (p)}
										{@const r = result(family, variant.id, p)}
										{#if r}
											{@const name = family.probes[p].effect_name}
											<tr class="border-b border-line last:border-0">
												<td class="py-2">{family.probes[p].title}</td>
												{#if r.inconclusive}
													<td colspan="4" class="py-2 text-right text-ink-2">{r.inconclusive}</td>
												{:else}
													<td class="num py-2 text-right">{fmtEffect(r.effect, name)}</td>
													<td class="num py-2 text-right text-ink-2"
														>{r.margin == null ? '—' : fmtEffect(r.margin, name)}</td
													>
													<td class="num py-2 text-right">{fmtP(r.p_value)}</td>
													<td class="num py-2 text-right">{fmtRequests(r.requests_for_95)}</td>
												{/if}
												<td class="py-2 pl-4">
													{#if variant.kind === 'cut'}
														<Status
															kind={r.flagged ? 'detected' : 'missed'}
															label={r.flagged ? 'Flagged' : 'Not flagged'}
														/>
													{:else}
														<Status kind={r.flagged ? 'false-alarm' : 'pass'} />
													{/if}
												</td>
											</tr>
										{/if}
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<LineChart
							{series}
							xLabel="Requests to both endpoints"
							yLabel={variant.kind === 'cut' ? 'Detection rate' : 'False-alarm rate'}
							threshold={variant.kind === 'cut' ? { y: 0.95, label: '95%' } : undefined}
						/>
					{/if}
				</div>
			</section>
		{/if}

		{#if sweepFamilies.length > 1}
			<section class="mt-14">
				<h2 class="text-xl font-semibold">Does detection get harder with model size?</h2>
				<p class="mt-1 max-w-3xl text-sm text-ink-2">
					Larger models often lose less quality to quantization, so the same cut can be harder to
					see. Requests needed for 95% detection of the same corner-cut, by model size. Flagship
					plan models are 100× larger still; read these as lower bounds on the cost of an audit.
				</p>
				<div class="mt-4 grid gap-4 md:grid-cols-2">
					{#each sweepCuts as cut (cut)}
						<div class="card overflow-x-auto">
							<table class="w-full text-sm">
								<caption class="px-4 pt-3 text-left text-sm font-medium"
									>{sweepFamilies[0].variants.find((v) => v.id === cut)?.label ?? cut}</caption
								>
								<thead class="text-xs text-muted">
									<tr class="border-b border-line">
										<th class="px-4 py-2 text-left font-medium">Probe</th>
										{#each sweepFamilies as f (f.family)}
											<th class="px-4 py-2 text-right font-medium">{f.params_b}B</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each sweepProbes as p (p)}
										<tr class="border-b border-line last:border-0">
											<td class="px-4 py-2">{sweepFamilies[0].probes[p]?.title ?? p}</td>
											{#each sweepFamilies as f (f.family)}
												{@const r = result(f, cut, p)}
												<td class="num px-4 py-2 text-right {r?.flagged ? '' : 'text-muted'}">
													{#if !r}—{:else if r.requests_for_95 != null}{fmtRequests(
															r.requests_for_95
														)}{:else if r.flagged}&gt;{fmtRequests(
															r.curve.at(-1)?.requests
														)}{:else}not seen{/if}
												</td>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<section class="mt-14 grid gap-8 md:grid-cols-2">
			<div>
				<h2 class="text-xl font-semibold">Margins</h2>
				<p class="mt-1 text-sm text-ink-2">
					The largest effect an honest variation produced, plus {Math.round(
						(family.headroom - 1) * 100
					)}% headroom, never below the probe’s default. Honest rows in the matrix are judged with a
					leave-one-out margin so their false-alarm rate is a real test.
				</p>
				<table class="mt-4 w-full text-sm">
					<tbody>
						{#each PROBES.filter((p) => p in family.probes) as p (p)}
							{@const pr = family.probes[p]}
							<tr class="border-b border-line last:border-0">
								<td class="py-2">{pr.title}</td>
								<td class="py-2 text-ink-2">{pr.effect_name}</td>
								<td class="num py-2 text-right"
									>{pr.margin == null ? '—' : fmtEffect(pr.margin, pr.effect_name)}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div>
				<h2 class="text-xl font-semibold">What this does not show</h2>
				<ul class="mt-3 list-disc space-y-2 pl-5 text-sm text-ink-2">
					<li>
						Production APIs add network jitter, batching with strangers and their own kernels. The
						honest variations stand in for that, but only partly. Audits run with
						<code class="inline">--calibrate</code> also compare each official API with itself and widen
						the margins to match.
					</li>
					<li>
						A provider who recognises audit traffic can serve it the real model. Panels are
						generated from a seed and can be rotated, and requests are paced like a person’s, but no
						black-box test is proof against a determined adversary.
					</li>
					<li>
						Subsampling one large run estimates power optimistically: the subsets share requests.
					</li>
				</ul>
				<a class="link mt-4 inline-block text-sm" href={resolve('/method')}>Full method →</a>
			</div>
		</section>
	{/if}
</div>
