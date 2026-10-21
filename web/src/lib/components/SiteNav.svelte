<script lang="ts">
	import { afterNavigate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { SITE } from '$lib/site';
	import ThemeToggle from './ThemeToggle.svelte';

	let open = $state(false);
	afterNavigate(() => (open = false));

	// Active state keys off the route id, so it is independent of the base path.
	const links = [
		{ href: resolve('/'), label: 'Directory', match: ['/', '/providers'] },
		{ href: resolve('/benchmarks/'), label: 'Benchmarks', match: ['/benchmarks'] },
		{ href: resolve('/methodology/'), label: 'Methodology', match: ['/methodology'] }
	];

	function isActive(match: string[]) {
		const id = page.route.id ?? '';
		return match.some((m) => (m === '/' ? id === '/' : id.startsWith(m)));
	}
</script>

<nav aria-label="Primary" class="border-b border-border bg-panel">
	<div class="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-12">
		<a
			href={resolve('/')}
			class="flex min-w-0 items-center gap-3 rounded-sm text-primary"
			aria-label="{SITE.name} — home"
		>
			<svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true" class="shrink-0">
				<rect width="32" height="32" rx="3" class="fill-primary" />
				<path d="M8 22h4V14H8zm6 0h4V9h-4zm6 0h4v-5h-4z" class="fill-panel" />
			</svg>
			<span class="truncate text-wordmark">{SITE.wordmark}</span>
		</a>
		<span
			class="hidden rounded-sm border border-border px-1.5 py-0.5 text-version text-muted uppercase sm:inline"
			>{SITE.version}</span
		>

		<ul class="ml-auto hidden h-16 items-stretch gap-8 md:flex">
			{#each links as link (link.href)}
				{@const active = isActive(link.match)}
				<li class="flex">
					<a
						href={link.href}
						aria-current={active ? 'page' : undefined}
						class={[
							'-mb-px flex items-center border-b-2 pt-0.5 text-nav',
							active
								? 'border-primary text-primary'
								: 'border-transparent text-muted hover:text-primary'
						]}>{link.label}</a
					>
				</li>
			{/each}
		</ul>

		<div class="ml-auto flex items-center gap-2 md:ml-4">
			<ThemeToggle />
			<button
				type="button"
				class="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-border text-primary md:hidden"
				aria-expanded={open}
				aria-controls="mobile-menu"
				aria-label={open ? 'Close menu' : 'Open menu'}
				onclick={() => (open = !open)}
			>
				<svg
					viewBox="0 0 16 16"
					width="14"
					height="14"
					aria-hidden="true"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
				>
					{#if open}
						<path d="M3 3l10 10M13 3L3 13" />
					{:else}
						<path d="M2 4h12M2 8h12M2 12h12" />
					{/if}
				</svg>
			</button>
		</div>
	</div>

	{#if open}
		<ul id="mobile-menu" class="border-t border-border px-4 py-2 md:hidden">
			{#each links as link (link.href)}
				{@const active = isActive(link.match)}
				<li>
					<a
						href={link.href}
						aria-current={active ? 'page' : undefined}
						class={[
							'flex items-center border-l-2 py-3 pl-3 text-nav',
							active ? 'border-primary text-primary' : 'border-transparent text-muted'
						]}>{link.label}</a
					>
				</li>
			{/each}
		</ul>
	{/if}
</nav>
