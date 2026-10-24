<script lang="ts">
	import { audits, dataPath, lab } from '#lib/data.ts';
	import { site } from '#lib/site.ts';
	import { asset } from '$app/paths';

	const files = [
		{ path: 'catalog.json', what: 'Providers, models, plans and which endpoints are compared.' },
		{ path: 'audits/index.json', what: 'Latest audit per plan and model.' },
		...lab.map((f) => ({
			path: `lab/${f.family}.json`,
			what: `Calibration lab: ${f.name}, every variant × probe, margins and power curves.`
		})),
		...audits.map((a) => ({
			path: `audits/${a.plan}/${a.target.slug}/${a.started_at.slice(0, 10)}_${a.tier}.json`,
			what: `Audit of ${a.target.slug} (${a.tier}).`
		}))
	];

	const steps = [
		['Install', 'uv sync'],
		['Check the toolchain offline', 'uv run planaudit selftest'],
		['Calibrate on a local GPU (vLLM)', 'uv run planaudit lab run --family qwen2.5-7b'],
		['Margins and power curves → data/lab/', 'uv run planaudit lab analyze'],
		[
			'Audit a plan (needs both API keys)',
			'uv run planaudit audit --plan zai-glm-coding-lite --tier quick'
		]
	];
</script>

<svelte:head>
	<title>Data — {site.name}</title>
</svelte:head>

<div class="mx-auto max-w-3xl px-4 pt-14 sm:px-6">
	<p class="eyebrow">Open data</p>
	<h1 class="mt-3 text-3xl font-semibold sm:text-4xl">Dataset and reproduction</h1>
	<p class="mt-4 text-ink-2">
		Everything on this site is generated from these files, which are versioned in the repository.
		They are plain JSON; field names match the code in <code class="inline">src/planaudit/</code>.
	</p>

	<ul class="card mt-8 divide-y divide-line">
		{#each files as f (f.path)}
			<li class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 py-3">
				<a class="link num text-sm" href={asset(dataPath(f.path) as 'robots.txt')} download
					>{f.path}</a
				>
				<span class="text-sm text-ink-2">{f.what}</span>
			</li>
		{/each}
	</ul>

	<h2 class="mt-14 text-2xl font-semibold">Reproduce it</h2>
	<p class="mt-2 text-sm text-ink-2">
		Python 3.11+ with <a class="link" href="https://docs.astral.sh/uv/">uv</a>. The lab additionally
		needs an NVIDIA GPU and vLLM in its own environment (see
		<code class="inline">config/lab.toml</code>).
	</p>
	<ol class="mt-6 space-y-4">
		{#each steps as [what, cmd], i (cmd)}
			<li>
				<p class="text-sm"><span class="num mr-2 text-muted">{i + 1}.</span>{what}</p>
				<pre
					class="num mt-1.5 overflow-x-auto rounded-md border border-line bg-surface px-3 py-2 text-xs">{cmd}</pre>
			</li>
		{/each}
	</ol>
	<p class="mt-8 text-sm text-ink-2">
		Source: <a class="link" href={site.repo}>{site.repo.replace('https://', '')}</a>
	</p>
</div>
