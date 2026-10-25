<script lang="ts">
	import Status from '#lib/components/Status.svelte';
	import {
		catalog,
		coverage,
		fmtPrice,
		modelBySlug,
		planStatus,
		priceRange,
		providerBySlug,
		type Plan
	} from '#lib/data.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	type Kind = 'all' | 'maker' | 'reseller';
	type Sort = 'price' | 'name' | 'coverage';
	let kind = $state<Kind>('all');
	let sort = $state<Sort>('price');
	let query = $state('');

	const riskLabel = { high: 'High', medium: 'Medium', low: 'Low', unknown: 'Unknown' } as const;
	const riskClass = {
		high: 'text-bad-ink',
		medium: 'text-warn-ink',
		low: 'text-good-ink',
		unknown: 'text-muted'
	} as const;

	const modelNames = (p: Plan) => p.models.map((m) => modelBySlug.get(m)?.name ?? m);
	const rows = $derived(
		catalog.plans
			.filter((p) => kind === 'all' || p.kind === kind)
			.filter((p) => {
				const q = query.trim().toLowerCase();
				if (!q) return true;
				const hay = [p.name, providerBySlug.get(p.provider)?.name ?? '', ...modelNames(p)]
					.join(' ')
					.toLowerCase();
				return hay.includes(q);
			})
			.sort((a, b) =>
				sort === 'price'
					? priceRange(a)[0] - priceRange(b)[0]
					: sort === 'coverage'
						? coverage(b.slug).runnable - coverage(a.slug).runnable
						: a.name.localeCompare(b.name)
			)
	);

	function priceLabel(p: Plan) {
		const t = [...p.tiers].sort((a, b) => a.price - b.price);
		const lo = t[0];
		return t.length > 1
			? `${fmtPrice(lo.price, lo.currency)}–${fmtPrice(t.at(-1)!.price, lo.currency)}`
			: fmtPrice(lo.price, lo.currency);
	}
	const approx = (p: Plan) =>
		p.tiers[0].currency === 'USD' ? null : `≈ $${Math.round(priceRange(p)[0])}+`;

	const makers = catalog.plans.filter((p) => p.kind === 'maker').length;
</script>

<svelte:head>
	<title>Coding plans compared — {site.name}</title>
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pt-14 sm:px-6">
	<p class="eyebrow">Directory · snapshot {catalog.snapshot}</p>
	<h1 class="mt-3 text-3xl font-semibold sm:text-4xl">Coding plans</h1>
	<p class="mt-3 max-w-2xl text-ink-2">
		{catalog.plans.length} flat-rate plans that hand you an API key for coding agents: {makers} sold by
		the model’s own maker, {catalog.plans.length - makers} by resellers serving someone else’s open-weight
		model. Each is paired with the official pay-per-token API it should match.
	</p>

	<div class="mt-8 flex flex-wrap items-center gap-3">
		<div
			class="inline-flex rounded-md border border-line bg-surface p-0.5"
			role="group"
			aria-label="Plan type"
		>
			{#each [['all', 'All'], ['maker', 'Model makers'], ['reseller', 'Resellers']] as [k, label] (k)}
				<button
					type="button"
					aria-pressed={kind === k}
					onclick={() => (kind = k as Kind)}
					class="rounded px-3 py-1.5 text-sm transition-colors {kind === k
						? 'bg-ink text-page'
						: 'text-ink-2 hover:text-ink'}">{label}</button
				>
			{/each}
		</div>
		<label class="relative min-w-48 flex-1 sm:max-w-xs">
			<span class="sr-only">Search plans, providers or models</span>
			<input
				type="search"
				bind:value={query}
				placeholder="Search plan, provider or model"
				class="w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm placeholder:text-muted focus:border-accent focus:outline-none"
			/>
		</label>
		<label class="ml-auto flex items-center gap-2 text-sm text-ink-2">
			Sort
			<select
				bind:value={sort}
				class="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink focus:border-accent focus:outline-none"
			>
				<option value="price">Lowest price</option>
				<option value="coverage">Most testable</option>
				<option value="name">Name</option>
			</select>
		</label>
	</div>

	<!-- Desktop: comparison table -->
	<div class="card mt-5 hidden overflow-hidden md:block">
		<table class="w-full text-left text-sm">
			<thead class="bg-sunken/60 text-xs text-muted">
				<tr>
					<th class="px-4 py-2.5 font-medium">Plan</th>
					<th class="px-4 py-2.5 font-medium">Price / month</th>
					<th class="px-4 py-2.5 font-medium">Audited model</th>
					<th class="px-4 py-2.5 font-medium" title="How many of our probes can run on this plan"
						>Testable</th
					>
					<th
						class="px-4 py-2.5 font-medium"
						title="Risk that automated testing breaks the plan's terms">ToS risk</th
					>
					<th class="px-4 py-2.5 font-medium">Result</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as p (p.slug)}
					{@const cov = coverage(p.slug)}
					<tr class="group border-t border-line hover:bg-sunken/50">
						<td class="px-4 py-3">
							<a
								href={resolve('/plans/[slug]', { slug: p.slug })}
								class="font-medium group-hover:text-accent">{p.name}</a
							>
							<div class="mt-0.5 flex items-center gap-1.5 text-xs text-ink-2">
								{providerBySlug.get(p.provider)?.name}
								<span class="rounded bg-sunken px-1.5 py-px text-[11px]"
									>{p.kind === 'maker' ? 'maker' : 'reseller'}</span
								>
							</div>
							{#if p.availability}<div class="mt-1 text-xs text-warn-ink">
									{p.availability}
								</div>{/if}
						</td>
						<td class="px-4 py-3">
							<span class="num whitespace-nowrap">{priceLabel(p)}</span>
							<div class="text-xs whitespace-nowrap text-muted">
								{p.tiers.length} tier{p.tiers.length > 1 ? 's' : ''}{#if approx(p)}
									· {approx(p)}{/if}
							</div>
						</td>
						<td class="px-4 py-3 text-ink-2">{modelNames(p).join(', ')}</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-2">
								<span class="flex gap-0.5" aria-hidden="true">
									{#each { length: cov.total }, i (i)}
										<span class="h-3 w-1.5 rounded-sm {i < cov.runnable ? 'bg-s1' : 'bg-grid'}"
										></span>
									{/each}
								</span>
								<span class="num text-xs text-ink-2">{cov.runnable}/{cov.total}</span>
							</div>
						</td>
						<td class="px-4 py-3 text-xs font-medium {riskClass[p.tos_risk]}"
							>{riskLabel[p.tos_risk]}</td
						>
						<td class="px-4 py-3"><Status kind={planStatus(p.slug)} /></td>
					</tr>
				{:else}
					<tr><td colspan="6" class="px-4 py-8 text-center text-ink-2">No plan matches.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Mobile: cards -->
	<div class="mt-5 space-y-3 md:hidden">
		{#each rows as p (p.slug)}
			{@const cov = coverage(p.slug)}
			<a href={resolve('/plans/[slug]', { slug: p.slug })} class="card block p-4">
				<div class="flex items-start justify-between gap-3">
					<div>
						<div class="font-medium">{p.name}</div>
						<div class="text-xs text-ink-2">{providerBySlug.get(p.provider)?.name} · {p.kind}</div>
					</div>
					<span class="num text-sm">{priceLabel(p)}</span>
				</div>
				<div class="mt-2 text-sm text-ink-2">{modelNames(p).join(', ')}</div>
				<div class="mt-3 flex items-center justify-between text-xs text-ink-2">
					<span
						>Testable {cov.runnable}/{cov.total} · ToS risk {riskLabel[
							p.tos_risk
						].toLowerCase()}</span
					>
					<Status kind={planStatus(p.slug)} />
				</div>
			</a>
		{:else}
			<p class="py-8 text-center text-ink-2">No plan matches.</p>
		{/each}
	</div>

	<div class="mt-6 grid gap-4 text-sm text-ink-2 md:grid-cols-3">
		<p>
			<span class="font-medium text-ink">Testable</span> counts the probes that can run on a plan. Models
			that always reason before answering, or endpoints that don’t document how to switch reasoning off,
			can only get the service-level checks for now.
		</p>
		<p>
			<span class="font-medium text-ink">ToS risk</span> is how plainly the plan’s terms restrict automated
			use. Audits keep volume low and identify themselves, but an account can still be suspended.
		</p>
		<p>
			Prices are a snapshot from {catalog.snapshot} and move monthly. CNY prices are converted at about
			${catalog.fx.CNY} per ¥1 for sorting only. Not listed: Claude, ChatGPT and Copilot subscriptions,
			which are not reachable as plain APIs (<a class="link" href={resolve('/method') + '#faq'}
				>why</a
			>).
		</p>
	</div>
</div>
