<script lang="ts">
	// A state, always as icon + word: color never carries the meaning alone.
	export type StatusKind =
		'match' | 'gap' | 'inconclusive' | 'untested' | 'detected' | 'missed' | 'false-alarm' | 'pass';

	let { kind, label }: { kind: StatusKind; label?: string } = $props();

	const spec = {
		match: { text: 'Matches API', cls: 'bg-good-wash text-good-ink', icon: 'check' },
		pass: { text: 'Pass', cls: 'bg-good-wash text-good-ink', icon: 'check' },
		detected: { text: 'Detected', cls: 'bg-good-wash text-good-ink', icon: 'check' },
		gap: { text: 'Gap found', cls: 'bg-bad-wash text-bad-ink', icon: 'alert' },
		'false-alarm': { text: 'False alarm', cls: 'bg-bad-wash text-bad-ink', icon: 'alert' },
		missed: { text: 'Missed', cls: 'bg-warn-wash text-warn-ink', icon: 'dash' },
		inconclusive: { text: 'Inconclusive', cls: 'bg-warn-wash text-warn-ink', icon: 'dash' },
		untested: { text: 'Not yet audited', cls: 'bg-sunken text-ink-2', icon: 'clock' }
	} as const;
	const s = $derived(spec[kind]);
</script>

<span
	class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap {s.cls}"
>
	<svg
		viewBox="0 0 16 16"
		class="size-3.5 shrink-0"
		fill="none"
		stroke="currentColor"
		stroke-width="1.8"
		aria-hidden="true"
	>
		{#if s.icon === 'check'}
			<path d="m3.5 8.5 3 3 6-7" stroke-linecap="round" stroke-linejoin="round" />
		{:else if s.icon === 'alert'}
			<path d="M8 4.5v4.5M8 11.5v.01" stroke-linecap="round" /><circle cx="8" cy="8" r="6.2" />
		{:else if s.icon === 'dash'}
			<path d="M4.5 8h7" stroke-linecap="round" />
		{:else}
			<circle cx="8" cy="8" r="6.2" /><path d="M8 4.8V8l2.2 1.4" stroke-linecap="round" />
		{/if}
	</svg>
	{label ?? s.text}
</span>
