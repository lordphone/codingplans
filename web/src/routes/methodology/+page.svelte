<script lang="ts">
	import { resolve } from '$app/paths';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import { familyLabel, TESTS } from '$lib/content/tests';
	import { SITE } from '$lib/site';

	const sections = [
		{ id: 'design', label: 'Reference vs plan' },
		{ id: 'stealth', label: 'Stealth client' },
		{ id: 'statistics', label: 'Statistics' },
		{ id: 'verdicts', label: 'Verdicts' },
		{ id: 'limits', label: 'What this cannot prove' },
		{ id: 'tests', label: 'Test catalogue' }
	];

	const families = [...new Set(TESTS.map((t) => t.family))];
</script>

<svelte:head>
	<title>Methodology · {SITE.name}</title>
	<meta
		name="description"
		content="How coding plans are audited: reference-vs-plan comparisons, stealth probing, Benjamini–Hochberg FDR control, and the limits of black-box detection."
	/>
</svelte:head>

<PageHeader eyebrow="How the audit works" title="Methodology">
	<p>
		Every number on this site comes from sending the same workload to two endpoints — the model
		vendor’s <strong class="font-semibold text-primary">official API</strong> and the
		<strong class="font-semibold text-primary">coding plan</strong> that claims to serve that model —
		and asking whether the plan’s behaviour is statistically distinguishable from the reference.
	</p>
</PageHeader>

<div class="mt-10 grid gap-10 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-14">
	<nav aria-label="On this page" class="lg:sticky lg:top-28 lg:self-start">
		<p class="text-eyebrow text-muted">On this page</p>
		<ol class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm lg:flex-col">
			{#each sections as s, i (s.id)}
				<li>
					<a href="#{s.id}" class="group flex gap-2 text-on-surface hover:text-accent-interactive">
						<span class="font-mono text-xs text-muted">{String(i + 1).padStart(2, '0')}</span>
						{s.label}
					</a>
				</li>
			{/each}
		</ol>
	</nav>

	<div class="min-w-0 space-y-14 text-[15px] leading-relaxed">
		<section id="design" aria-labelledby="h-design" class="scroll-mt-28">
			<h2 id="h-design" class="text-xl font-semibold tracking-tight text-primary">
				Reference vs plan
			</h2>
			<div class="mt-4 max-w-3xl space-y-4">
				<p>
					Each test is run <em>once per endpoint</em>, independently. A run hits exactly one
					endpoint and writes a self-describing artifact: the prompt panel id and hash, sample
					count, token limits and per-prompt outcomes. One official-API run for a model is reused as
					the reference for every plan that sells that model.
				</p>
				<p>
					Comparison is an offline, pure function of two artifacts. It refuses to compare runs whose
					panel, prompt hash, sample count or token limits differ — so a number on this site is
					always an apples-to-apples comparison of the same prompts under the same settings.
				</p>
				<ol
					class="grid gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-3"
				>
					{#each [['1', 'Reference run', 'Official API, fixed panel, recorded once per model.'], ['2', 'Plan run', 'Same panel against the plan endpoint, days apart if needed.'], ['3', 'Compare', 'Offline; no API calls. Exit pass / fail / incomparable.']] as [n, title, body] (n)}
						<li class="bg-panel p-4">
							<p class="font-mono text-xs text-muted">STEP {n}</p>
							<p class="mt-1 font-semibold text-primary">{title}</p>
							<p class="mt-1 text-sm text-muted">{body}</p>
						</li>
					{/each}
				</ol>
			</div>
		</section>

		<section id="stealth" aria-labelledby="h-stealth" class="scroll-mt-28">
			<h2 id="h-stealth" class="text-xl font-semibold tracking-tight text-primary">
				Stealth client
			</h2>
			<div class="mt-4 max-w-3xl space-y-4">
				<p>
					A provider that can recognise audit traffic can route it to the genuine model. The client
					therefore looks like ordinary usage: rotated user agents, jittered pacing between calls,
					and a shuffled request schedule so the panel is never sent in a recognisable order. Batch
					APIs are never used.
				</p>
				<p>
					Pacing and schedule seed are stealth knobs only — they are recorded but do not affect
					whether two runs are comparable. Prompt panels are versioned; changing the content bumps
					the panel id and invalidates old artifacts.
				</p>
			</div>
		</section>

		<section id="statistics" aria-labelledby="h-statistics" class="scroll-mt-28">
			<h2 id="h-statistics" class="text-xl font-semibold tracking-tight text-primary">
				Statistics
			</h2>
			<div class="mt-4 max-w-3xl space-y-4">
				<p>
					Every test is <strong class="font-semibold text-primary">two-sided</strong>: a plan that
					is suspiciously <em>better</em> than the reference is as interesting as one that is worse. Rates
					(tool-call validity, unit-test pass rate, needle recall) use a two-proportion test with a Fisher
					exact fallback for small cells; per-sample scores (token counts, reasoning lengths) use a permutation
					test on the mean.
				</p>
				<p>
					An audit runs many tests at once, so raw p-values would produce false alarms. p-values are
					adjusted with the
					<strong class="font-semibold text-primary">Benjamini–Hochberg</strong> procedure across the
					tests of each audit (one plan × model × date), controlling the false discovery rate.
				</p>
				<dl
					class="grid gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-2"
				>
					<div class="bg-panel p-4">
						<dt class="text-eyebrow text-muted">A test fails when</dt>
						<dd class="mt-2 text-sm">
							the gap exceeds the test’s minimum effect threshold <em>and</em> its BH-adjusted
							q-value is below <span class="font-mono text-primary">0.05</span>.
						</dd>
					</div>
					<div class="bg-panel p-4">
						<dt class="text-eyebrow text-muted">A test is inconclusive when</dt>
						<dd class="mt-2 text-sm">
							either side has too few usable samples, or required fields (e.g. usage counts) are
							missing. Run failures (auth errors, rate-limit storms) are reported as errors.
						</dd>
					</div>
				</dl>
			</div>
		</section>

		<section id="verdicts" aria-labelledby="h-verdicts" class="scroll-mt-28">
			<h2 id="h-verdicts" class="text-xl font-semibold tracking-tight text-primary">Verdicts</h2>
			<div class="mt-4 max-w-3xl space-y-4">
				<p>
					Integrity is summarised from the <em>latest</em> result of each test for each model on a plan.
					A plan’s verdict aggregates its models.
				</p>
				<ul class="divide-y divide-border rounded-sm border border-border bg-panel">
					<li class="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4">
						<span class="sm:w-36"><StatusBadge kind="verdict" value="flagged" /></span>
						<span class="text-sm">At least one test failed after correction.</span>
					</li>
					<li class="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4">
						<span class="sm:w-36"><StatusBadge kind="verdict" value="verified" /></span>
						<span class="text-sm">Every latest test passed (and at least one exists).</span>
					</li>
					<li class="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4">
						<span class="sm:w-36"><StatusBadge kind="verdict" value="partial" /></span>
						<span class="text-sm">No failures, but some tests are inconclusive or errored.</span>
					</li>
					<li class="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4">
						<span class="sm:w-36"><StatusBadge kind="verdict" value="untested" /></span>
						<span class="text-sm">No audit results published yet.</span>
					</li>
				</ul>
				<p>
					The separate <strong class="font-semibold text-primary">quantization</strong> label (<span
						class="font-mono text-sm">Standard</span
					>
					/
					<span class="font-mono text-sm">Aggressive quant</span> /
					<span class="font-mono text-sm">Untested</span>) is the most recent non-empty quantization
					finding recorded with speed probes. Speed figures are rolling 30-day means of per-session
					throughput (output tokens per second) and time to first token, with p10 / p90 tails.
				</p>
			</div>
		</section>

		<section id="limits" aria-labelledby="h-limits" class="scroll-mt-28">
			<h2 id="h-limits" class="text-xl font-semibold tracking-tight text-primary">
				What this cannot prove
			</h2>
			<div class="mt-4 max-w-3xl space-y-4">
				<div class="rounded-sm border-l-2 border-primary bg-panel py-3 pr-4 pl-4">
					<p class="font-semibold text-primary">This is a drift detector, not a proof.</p>
					<p class="mt-1 text-sm">
						Text-only black-box auditing detects an FP8/INT8 substitution of the same base model at
						roughly chance accuracy (Cai et al., “Are You Getting What You Pay For?”, arXiv
						2504.04715). A pass means we found no difference we could measure — not that the plan
						serves full-precision weights.
					</p>
				</div>
				<ul class="list-disc space-y-2 pl-5 marker:text-muted">
					<li>
						Aggressive quantization, model swaps, truncation and broken tool calls leave larger
						fingerprints and are what the suite is tuned to catch.
					</li>
					<li>
						Greedy (temperature 0) outputs are not perfectly deterministic even on official APIs;
						tests are designed around that noise floor.
					</li>
					<li>
						Results are point-in-time samples from one vantage point. Providers can change serving
						at any moment; check the run date on every result.
					</li>
					<li>A failure is a statistical signal about behaviour, not a claim about intent.</li>
				</ul>
			</div>
		</section>

		<section id="tests" aria-labelledby="h-tests" class="scroll-mt-28">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 id="h-tests" class="text-xl font-semibold tracking-tight text-primary">
					Test catalogue
				</h2>
				<p class="font-mono text-xs text-muted">
					{TESTS.length} tests · {families.length} families
				</p>
			</div>
			<div class="mt-6 grid gap-4 xl:grid-cols-2">
				{#each TESTS as t (t.id)}
					<article
						id={t.id}
						class="scroll-mt-28 rounded-sm border border-border bg-panel p-5 shadow-sm target:border-accent-interactive target:ring-1 target:ring-accent-interactive"
						aria-labelledby="t-{t.id}"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<p class="text-eyebrow text-muted">{familyLabel(t.family)}</p>
								<h3 id="t-{t.id}" class="mt-1 text-base font-semibold text-primary">{t.name}</h3>
							</div>
							<a
								href="#{t.id}"
								class="shrink-0 rounded-sm border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted hover:border-accent-interactive hover:text-primary"
								aria-label="Link to {t.name}">{t.id}</a
							>
						</div>
						<dl class="mt-4 grid gap-3 text-sm sm:grid-cols-[6.5rem_minmax(0,1fr)]">
							<dt class="pt-0.5 text-eyebrow text-muted">Threat</dt>
							<dd>{t.threat}</dd>
							<dt class="pt-0.5 text-eyebrow text-muted">How</dt>
							<dd>{t.how}</dd>
							<dt class="pt-0.5 text-eyebrow text-muted">Signal</dt>
							<dd>{t.signal}</dd>
							<dt class="pt-0.5 text-eyebrow text-muted">Limitation</dt>
							<dd class="text-muted">{t.limitation}</dd>
						</dl>
					</article>
				{/each}
			</div>
			<p class="mt-8 text-sm">
				<a class="link" href={resolve('/')}>← Back to the directory</a>
			</p>
		</section>
	</div>
</div>
