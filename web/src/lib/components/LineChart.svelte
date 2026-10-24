<script lang="ts" module>
	export type Series = {
		id: string;
		label: string;
		color: string; // a CSS color, normally var(--s1)…var(--s8) or var(--muted)
		points: { x: number; y: number | null }[];
		muted?: boolean;
	};
</script>

<script lang="ts">
	// Multi-series line chart on a log-x / linear-y plane, with a crosshair
	// tooltip, a legend, and end labels for up to four highlighted series.
	let {
		series,
		xLabel,
		yLabel,
		yMax = 1,
		yFormat = (v: number) => `${Math.round(v * 100)}%`,
		xFormat = (v: number) => (v >= 1000 ? `${+(v / 1000).toFixed(1)}K` : `${v}`),
		height = 260,
		threshold
	}: {
		series: Series[];
		xLabel: string;
		yLabel: string;
		yMax?: number;
		yFormat?: (v: number) => string;
		xFormat?: (v: number) => string;
		height?: number;
		threshold?: { y: number; label: string };
	} = $props();

	let width = $state(640);
	let hoverX = $state<number | null>(null);

	const m = { top: 14, right: 18, bottom: 42, left: 46 };
	const xs = $derived(series.flatMap((s) => s.points.map((p) => p.x)).filter((x) => x > 0));
	const xMin = $derived(Math.min(...xs));
	const xMax = $derived(Math.max(...xs));
	const innerW = $derived(Math.max(10, width - m.left - m.right));
	const innerH = $derived(height - m.top - m.bottom);

	const lx = (x: number) => Math.log10(x);
	const sx = (x: number) =>
		m.left + (xMax === xMin ? innerW / 2 : ((lx(x) - lx(xMin)) / (lx(xMax) - lx(xMin))) * innerW);
	const sy = (y: number) => m.top + innerH - (y / yMax) * innerH;

	const xTicks = $derived.by(() => {
		const out: number[] = [];
		for (let e = Math.floor(lx(xMin)); e <= Math.ceil(lx(xMax)); e++) {
			for (const f of [1, 3]) {
				const v = f * 10 ** e;
				if (v >= xMin * 0.999 && v <= xMax * 1.001) out.push(v);
			}
		}
		return out;
	});
	const yTicks = $derived([0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax));

	function path(points: Series['points']) {
		let d = '';
		let pen = false;
		for (const p of points) {
			if (p.y == null) {
				pen = false;
				continue;
			}
			d += `${pen ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`;
			pen = true;
		}
		return d;
	}

	// Snap the crosshair to the nearest x that any series has a point at.
	const allX = $derived([...new Set(xs)].sort((a, b) => a - b));
	function onMove(e: PointerEvent) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const px = e.clientX - rect.left;
		let best = allX[0];
		for (const x of allX) if (Math.abs(sx(x) - px) < Math.abs(sx(best) - px)) best = x;
		hoverX = best;
	}
	const hoverRows = $derived(
		hoverX == null
			? []
			: series
					.map((s) => ({ s, p: s.points.find((p) => p.x === hoverX) }))
					.filter((r) => r.p && r.p.y != null)
					.sort((a, b) => b.p!.y! - a.p!.y!)
	);

	const labelled = $derived(
		series
			.filter((s) => !s.muted)
			.slice(0, 4)
			.map((s) => {
				const last = [...s.points].reverse().find((p) => p.y != null);
				return last ? { s, x: sx(last.x), y: sy(last.y!) } : null;
			})
			.filter((v) => v != null)
	);
</script>

<div class="relative" bind:clientWidth={width}>
	<svg
		{width}
		{height}
		role="img"
		aria-label="{yLabel} by {xLabel}"
		class="block touch-none select-none"
		onpointermove={onMove}
		onpointerleave={() => (hoverX = null)}
	>
		{#each yTicks as t (t)}
			<line x1={m.left} x2={m.left + innerW} y1={sy(t)} y2={sy(t)} class="stroke-grid" />
			<text
				x={m.left - 8}
				y={sy(t)}
				dy="0.32em"
				text-anchor="end"
				class="num fill-muted text-[11px]">{yFormat(t)}</text
			>
		{/each}
		{#each xTicks as t (t)}
			<text
				x={sx(t)}
				y={m.top + innerH + 18}
				text-anchor="middle"
				class="num fill-muted text-[11px]">{xFormat(t)}</text
			>
		{/each}
		<line
			x1={m.left}
			x2={m.left + innerW}
			y1={m.top + innerH}
			y2={m.top + innerH}
			class="stroke-axis"
		/>
		<text x={m.left + innerW / 2} y={height - 4} text-anchor="middle" class="fill-ink-2 text-[11px]"
			>{xLabel}</text
		>

		{#if threshold}
			<line
				x1={m.left}
				x2={m.left + innerW}
				y1={sy(threshold.y)}
				y2={sy(threshold.y)}
				class="stroke-ink-2"
				stroke-opacity="0.45"
			/>
			<text x={m.left + 4} y={sy(threshold.y) - 5} class="fill-ink-2 text-[10px]"
				>{threshold.label}</text
			>
		{/if}

		{#each series.filter((s) => s.muted) as s (s.id)}
			<path
				d={path(s.points)}
				fill="none"
				stroke={s.color}
				stroke-width="1.5"
				stroke-opacity="0.7"
				stroke-linejoin="round"
				stroke-linecap="round"
			/>
		{/each}
		{#each series.filter((s) => !s.muted) as s (s.id)}
			<path
				d={path(s.points)}
				fill="none"
				stroke={s.color}
				stroke-width="2"
				stroke-linejoin="round"
				stroke-linecap="round"
			/>
		{/each}

		{#each labelled as l (l.s.id)}
			<circle cx={l.x} cy={l.y} r="4" fill={l.s.color} class="stroke-surface" stroke-width="2" />
		{/each}

		{#if hoverX != null}
			<line x1={sx(hoverX)} x2={sx(hoverX)} y1={m.top} y2={m.top + innerH} class="stroke-axis" />
			{#each hoverRows as r (r.s.id)}
				<circle
					cx={sx(hoverX)}
					cy={sy(r.p!.y!)}
					r="4"
					fill={r.s.color}
					class="stroke-surface"
					stroke-width="2"
				/>
			{/each}
		{/if}
	</svg>

	{#if hoverX != null && hoverRows.length}
		<div
			class="pointer-events-none absolute top-2 z-10 min-w-44 rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-lg"
			style:left="{Math.min(sx(hoverX) + 12, width - 200)}px"
		>
			<div class="mb-1 font-medium text-ink">{xFormat(hoverX)} {xLabel.toLowerCase()}</div>
			{#each hoverRows as r (r.s.id)}
				<div class="flex items-center justify-between gap-4 text-ink-2">
					<span class="flex items-center gap-1.5"
						><span class="size-2 rounded-full" style:background={r.s.color}></span>{r.s.label}</span
					>
					<span class="num text-ink">{yFormat(r.p!.y!)}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2" aria-label="Legend">
	{#each series as s (s.id)}
		<li class="flex items-center gap-1.5">
			<span
				class="h-0.5 w-3.5 rounded-full"
				style:background={s.color}
				style:opacity={s.muted ? 0.7 : 1}
			></span>{s.label}
		</li>
	{/each}
</ul>
