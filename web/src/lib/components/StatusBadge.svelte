<script lang="ts" module>
	import type { AuditStatus, QuantStatus, Verdict } from '$lib/data/types';

	export type BadgeProps =
		| { kind: 'verdict'; value: Verdict; size?: 'sm' | 'md' }
		| { kind: 'status'; value: AuditStatus; size?: 'sm' | 'md' }
		| { kind: 'quant'; value: QuantStatus; size?: 'sm' | 'md' };
</script>

<script lang="ts">
	import { QUANT_LABEL, STATUS_LABEL, VERDICT_LABEL } from '$lib/format';

	let props: BadgeProps = $props();

	type Tone = 'positive' | 'negative' | 'neutral' | 'muted';

	const view = $derived.by((): { label: string; tone: Tone; glyph: string } => {
		switch (props.kind) {
			case 'verdict':
				return {
					label: VERDICT_LABEL[props.value],
					tone:
						props.value === 'verified'
							? 'positive'
							: props.value === 'flagged'
								? 'negative'
								: props.value === 'partial'
									? 'neutral'
									: 'muted',
					glyph: { verified: '✓', flagged: '✕', partial: '◐', untested: '○' }[props.value]
				};
			case 'status':
				return {
					label: STATUS_LABEL[props.value],
					tone:
						props.value === 'pass' ? 'positive' : props.value === 'fail' ? 'negative' : 'neutral',
					glyph: { pass: '✓', fail: '✕', inconclusive: '?', error: '!' }[props.value]
				};
			case 'quant':
				return {
					label: QUANT_LABEL[props.value],
					tone:
						props.value === 'standard'
							? 'positive'
							: props.value === 'aggressive'
								? 'negative'
								: 'muted',
					glyph: { standard: '✓', aggressive: '✕', untested: '○' }[props.value]
				};
		}
	});

	const toneClass: Record<Tone, string> = {
		positive: 'border-secondary/35 bg-secondary-container text-secondary',
		negative: 'border-tertiary/35 bg-tertiary-container text-tertiary',
		neutral: 'border-border-strong bg-neutral text-on-surface',
		muted: 'border-dashed border-border-strong bg-transparent text-muted'
	};
</script>

<span
	class={[
		'inline-flex shrink-0 items-center gap-1.5 rounded-sm border font-mono leading-none font-semibold tracking-wider whitespace-nowrap uppercase',
		props.size === 'md' ? 'px-2 py-1 text-[11px]' : 'px-1.5 py-[3px] text-[10px]',
		toneClass[view.tone]
	]}
>
	<span aria-hidden="true">{view.glyph}</span>{view.label}
</span>
