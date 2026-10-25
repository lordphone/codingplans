<script lang="ts">
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	const related = [
		{
			name: 'Artificial Analysis — Endpoint Accuracy Index',
			what: 'Compares pay-per-token API endpoints of open-weight models against its own copy of the official weights.',
			diff: 'Covers APIs, not subscription plans; no caching or time-of-day checks.'
		},
		{
			name: 'Kimi Vendor Verifier (Moonshot)',
			what: 'Moonshot’s test suite for third-party hosts of its Kimi models.',
			diff: 'Checks other vendors, not Moonshot’s own Kimi Code plan.'
		},
		{
			name: 'Drift trackers (AI Stupid Level, IsItNerfed)',
			what: 'Track quality of official APIs over time.',
			diff: 'Official APIs only; no plan-versus-API comparison.'
		},
		{
			name: 'OpenRouter',
			what: 'Routes between providers and shows their quantization labels.',
			diff: 'Relies on what providers declare.'
		},
		{
			name: 'Price comparison sites',
			what: 'List plan prices and quotas.',
			diff: 'No measurement; some earn affiliate fees.'
		}
	];
</script>

<svelte:head>
	<title>About — {site.name}</title>
</svelte:head>

<article class="mx-auto max-w-3xl px-4 pt-14 sm:px-6">
	<p class="eyebrow">About</p>
	<h1 class="mt-3 text-3xl font-semibold sm:text-4xl">An independent check on coding plans</h1>
	<div class="prose-body mt-6 text-ink-2">
		<p>
			Flat-rate coding plans are cheap because the provider bets you will use less than you pay for,
			and because serving can be made cheaper: smaller numbers in the weights, shorter context, a
			smaller model when it’s busy. Most of that is invisible to the person typing. {site.name} makes
			it visible by measuring each plan against the same provider’s pay-per-token API, the product whose
			quality the provider is most accountable for.
		</p>
		<p>
			The method is the contribution. It is validated on known corner-cuts before it is pointed at a
			real plan, and it is published in full so the results can be checked, rerun and argued with.
		</p>
	</div>

	<section class="mt-12">
		<h2 class="text-xl font-semibold">Independence and funding</h2>
		<ul class="mt-4 list-disc space-y-2.5 pl-5 text-sm text-ink-2">
			<li>No provider pays for, reviews or receives results before publication.</li>
			<li>No affiliate links and no referral fees, now or later.</li>
			<li>
				Audit accounts are bought at list price, like any customer’s. Free plans or credits from a
				provider under audit are never used: the provider would know those accounts.
			</li>
			<li>
				Running costs (plan subscriptions, API usage, GPU time) are currently paid by the
				maintainer. Any outside funding will be listed on this page, with its source.
			</li>
		</ul>
	</section>

	<section class="mt-12">
		<h2 class="text-xl font-semibold">Corrections and right of reply</h2>
		<div class="prose-body mt-3 text-sm text-ink-2">
			<p>
				If you think a result is wrong, open an issue on the
				<a class="link" href="{site.repo}/issues">project’s GitHub</a> with what you believe and why.
				A provider can also ask for a re-test, explain a difference (for example a disclosed limit), or
				reply in writing. Replies and corrections are published next to the result they concern, and a
				corrected result keeps its history.
			</p>
		</div>
	</section>

	<section class="mt-12">
		<h2 class="text-xl font-semibold">Testing responsibly</h2>
		<div class="prose-body mt-3 text-sm text-ink-2">
			<p>
				Several plans restrict automated use in their terms. Audits are low-volume, paced like a
				person’s usage, and send an honest User-Agent rather than imitating a coding tool. Each
				plan’s page states how plainly its terms restrict this kind of testing.
			</p>
		</div>
	</section>

	<section class="mt-12">
		<h2 class="text-xl font-semibold">How this differs from existing work</h2>
		<div class="mt-4 divide-y divide-line border-y border-line">
			{#each related as r (r.name)}
				<div class="grid gap-1 py-4 sm:grid-cols-[14rem_1fr] sm:gap-6">
					<div class="font-medium">{r.name}</div>
					<div class="text-sm text-ink-2">
						{r.what} <span class="text-ink">{r.diff}</span>
					</div>
				</div>
			{/each}
		</div>
		<p class="mt-4 text-sm text-ink-2">
			As far as we know, nobody else compares coding plans with their provider’s own API, and nobody
			checks whether reported prompt caching is real.
		</p>
	</section>

	<section class="mt-12">
		<h2 class="text-xl font-semibold">Open source</h2>
		<p class="mt-3 text-sm text-ink-2">
			Code, lab configuration and data: <a class="link" href={site.repo}
				>{site.repo.replace('https://', '')}</a
			>. The <a class="link" href={resolve('/data')}>dataset page</a> lists every published file and how
			to reproduce it.
		</p>
	</section>
</article>
