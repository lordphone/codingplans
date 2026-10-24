<script lang="ts">
	import Status from '#lib/components/Status.svelte';
	import { auditsForPlan, catalog, modelBySlug, planStatus } from '#lib/data.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	const byProvider = catalog.providers
		.map((pr) => ({ pr, plans: catalog.plans.filter((p) => p.provider === pr.slug) }))
		.filter((g) => g.plans.length);
	const risk = { high: 'High', medium: 'Medium', low: 'Low', unknown: 'Unknown' } as const;
</script>

<svelte:head>
	<title>Plans — {site.name}</title>
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pt-14 sm:px-6">
	<p class="eyebrow">Catalog snapshot {catalog.snapshot}</p>
	<h1 class="mt-3 text-3xl font-semibold sm:text-4xl">Plans</h1>
	<p class="mt-3 max-w-2xl text-ink-2">
		Flat-rate subscriptions and the official pay-per-token API each one is held against. Prices and
		limits change often; check the provider’s page before buying.
	</p>

	<div class="mt-10 space-y-12">
		{#each byProvider as { pr, plans } (pr.slug)}
			<section>
				<div class="flex items-baseline justify-between gap-4 border-b border-line pb-2">
					<h2 class="text-lg font-semibold">{pr.name}</h2>
					<a class="link text-sm" href={pr.url} rel="external">Provider site ↗</a>
				</div>
				<div class="mt-4 grid gap-4 md:grid-cols-2">
					{#each plans as p (p.slug)}
						<a
							href={resolve('/plans/[slug]', { slug: p.slug })}
							class="card group block p-5 transition-colors hover:border-ink/25"
						>
							<div class="flex items-start justify-between gap-3">
								<div>
									<h3 class="font-medium group-hover:text-accent">{p.name}</h3>
									<p class="num mt-0.5 text-sm text-ink-2">{p.price} {p.currency} / month</p>
								</div>
								<Status kind={planStatus(p.slug)} />
							</div>
							<p class="mt-3 text-sm text-ink-2">{p.limits}</p>
							<div class="mt-4 flex flex-wrap gap-1.5">
								{#each auditsForPlan(p.slug) as a (a.target.slug)}
									<span class="rounded bg-sunken px-2 py-0.5 text-xs text-ink-2"
										>{modelBySlug.get(a.target.model ?? '')?.name ?? a.target.model}</span
									>
								{/each}
							</div>
							<p class="mt-4 text-xs text-muted">
								Terms-of-service risk for automated testing: <span class="text-ink-2"
									>{risk[p.tos_risk]}</span
								>
							</p>
						</a>
					{/each}
				</div>
			</section>
		{/each}
	</div>
</div>
