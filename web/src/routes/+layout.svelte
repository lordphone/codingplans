<script lang="ts">
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import ThemeToggle from '#lib/components/ThemeToggle.svelte';
	import { nav, site } from '#lib/site.ts';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const active = (href: string) => page.url.pathname.startsWith(resolve(href as '/plans'));
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<meta name="description" content={site.description} />
</svelte:head>

<a
	href="#main"
	class="sr-only rounded bg-ink px-3 py-2 text-page focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50"
	>Skip to content</a
>

<div class="flex min-h-dvh flex-col">
	<header class="sticky top-0 z-40 border-b border-line bg-page/85 backdrop-blur-md">
		<div class="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
			<a href={resolve('/')} class="flex items-center gap-2.5 font-semibold tracking-tight">
				<svg viewBox="0 0 32 32" class="size-6" aria-hidden="true">
					<rect width="32" height="32" rx="7" class="fill-ink" />
					<path
						d="M8 17.5h5l2.5-7 3 12 2.5-5H24"
						fill="none"
						class="stroke-page"
						stroke-width="2.4"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>
				<span>{site.name}</span>
			</a>
			<nav aria-label="Main" class="ml-auto flex items-center gap-0.5 sm:gap-1">
				{#each nav as item (item.href)}
					<a
						href={resolve(item.href)}
						aria-current={active(item.href) ? 'page' : undefined}
						class="rounded-md px-2 py-1.5 text-sm text-ink-2 transition-colors hover:bg-sunken hover:text-ink aria-[current=page]:font-medium aria-[current=page]:text-ink sm:px-3"
						>{item.label}</a
					>
				{/each}
				<span class="mx-1 h-5 w-px bg-line"></span>
				<ThemeToggle />
			</nav>
		</div>
	</header>

	<main id="main" class="flex-1">
		{@render children()}
	</main>

	<footer class="mt-24 border-t border-line">
		<div
			class="mx-auto grid max-w-6xl gap-6 px-4 py-10 text-sm text-ink-2 sm:grid-cols-[1fr_auto] sm:px-6"
		>
			<div class="max-w-xl space-y-2">
				<p class="font-medium text-ink">{site.name}</p>
				<p>
					Measured differences, not accusations. Every number on this site comes from published code
					and a public dataset; a difference can have honest causes, and plans may disclose some
					limits.
				</p>
			</div>
			<div class="flex gap-5 sm:flex-col sm:items-end sm:gap-1.5">
				<a class="link" href={resolve('/method')}>Method</a>
				<a class="link" href={resolve('/data')}>Dataset</a>
				<a class="link" href={site.repo}>Source code</a>
			</div>
		</div>
	</footer>
</div>
