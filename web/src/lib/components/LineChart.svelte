<script lang="ts">
	import { fmtDate, fmtDateShort, fmtNum } from '$lib/format';

	/**
	 * Single-series daily line chart (hand-rolled SVG). One measure per chart —
	 * TPS and TTFT get separate charts, never a dual axis.
	 */
	let {
		points,
		label,
		unit,
		color,
		digits = 1,
		height = 200
	}: {
		points: { day: string; value: number | null; runs?: number }[];
		label: string;
		unit: string;
		color: 'throughput' | 'latency';
		digits?: number;
		height?: number;
	} = $props();

	let width = $state(640);
	let active = $state<number | null>(null);

	const M = { top: 14, right: 14, bottom: 26, left: 44 };
	const stroke = $derived(
		color === 'throughput' ? 'var(--color-chart-throughput)' : 'var(--color-chart-latency)'
	);

	const values = $derived(points.map((p) => p.value).filter((v): v is number => v !== null));
	const mean = $derived(values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);

	/** A "nice" tick step (1, 2, 2.5, 5 × 10^k) giving roughly four intervals. */
	function niceStep(v: number): number {
		if (!(v > 0)) return 1;
		const raw = v / 4;
		const exp = 10 ** Math.floor(Math.log10(raw));
		const f = raw / exp;
		return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * exp;
	}

	const yStep = $derived(niceStep(Math.max(...values, 0) * 1.05));
	const yMax = $derived(yStep * Math.max(1, Math.ceil((Math.max(...values, 0) * 1.05) / yStep)));
	const yTicks = $derived(
		Array.from({ length: Math.round(yMax / yStep) + 1 }, (_, i) => +(i * yStep).toFixed(6))
	);
	const yDigits = $derived(
		Number.isInteger(yStep) ? 0 : Number.isInteger(+(yStep * 10).toFixed(6)) ? 1 : 2
	);
	const innerW = $derived(Math.max(10, width - M.left - M.right));
	const innerH = $derived(height - M.top - M.bottom);

	const t0 = $derived(points.length ? Date.parse(points[0].day) : 0);
	const t1 = $derived(points.length ? Date.parse(points[points.length - 1].day) : 1);
	const x = (day: string) =>
		M.left + (t1 === t0 ? innerW / 2 : ((Date.parse(day) - t0) / (t1 - t0)) * innerW);
	const y = (v: number) => M.top + innerH - (v / yMax) * innerH;

	/** Line path with gaps at null values. */
	const linePath = $derived.by(() => {
		let d = '';
		let pen = false;
		for (const p of points) {
			if (p.value === null) {
				pen = false;
				continue;
			}
			d += `${pen ? 'L' : 'M'}${x(p.day).toFixed(1)},${y(p.value).toFixed(1)}`;
			pen = true;
		}
		return d;
	});

	const areaPath = $derived.by(() => {
		const pts = points.filter((p) => p.value !== null);
		if (pts.length < 2) return '';
		const base = y(0).toFixed(1);
		return (
			`M${x(pts[0].day).toFixed(1)},${base}` +
			pts.map((p) => `L${x(p.day).toFixed(1)},${y(p.value!).toFixed(1)}`).join('') +
			`L${x(pts[pts.length - 1].day).toFixed(1)},${base}Z`
		);
	});

	const xTicks = $derived.by(() => {
		if (points.length === 0) return [];
		const n = width < 420 ? 3 : 5;
		if (points.length <= n) return points.map((p) => p.day);
		return Array.from(
			{ length: n },
			(_, i) => points[Math.round((i * (points.length - 1)) / (n - 1))].day
		);
	});

	const summary = $derived(
		values.length
			? `${label}: ${points.length} days, 30-day mean ${fmtNum(mean, digits)} ${unit}, range ${fmtNum(Math.min(...values), digits)}–${fmtNum(Math.max(...values), digits)} ${unit}.`
			: `${label}: no measurements in the window.`
	);

	function onMove(e: PointerEvent) {
		const svg = e.currentTarget as SVGSVGElement;
		const rect = svg.getBoundingClientRect();
		const px = ((e.clientX - rect.left) / rect.width) * width;
		let best = -1;
		let bestD = Infinity;
		points.forEach((p, i) => {
			if (p.value === null) return;
			const d = Math.abs(x(p.day) - px);
			if (d < bestD) {
				bestD = d;
				best = i;
			}
		});
		active = best >= 0 ? best : null;
	}

	function onKey(e: KeyboardEvent) {
		if (!points.length) return;
		const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
		if (e.key === 'Escape') {
			active = null;
			return;
		}
		if (!step) return;
		e.preventDefault();
		let i = active ?? (step > 0 ? -1 : points.length);
		do i += step;
		while (i >= 0 && i < points.length && points[i].value === null);
		if (i >= 0 && i < points.length) active = i;
	}

	const tip = $derived(active !== null ? points[active] : null);
	const tipLeft = $derived(tip ? Math.min(Math.max(x(tip.day), 70), width - 70) : 0);
</script>

<figure class="min-w-0">
	<figcaption class="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
		<span class="flex items-center gap-2 text-sm font-semibold text-primary">
			<span class="inline-block h-0.5 w-4" style:background={stroke} aria-hidden="true"></span>
			{label}
			<span class="font-mono text-xs font-normal text-muted">({unit})</span>
		</span>
		<span class="font-mono text-xs text-muted"
			>30-day mean <span class="text-primary">{fmtNum(mean, digits)}</span></span
		>
	</figcaption>

	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
	<div
		class="relative rounded-sm"
		bind:clientWidth={width}
		tabindex="0"
		role="group"
		aria-label="{summary} Use left and right arrow keys to read daily values."
		onkeydown={onKey}
		onblur={() => (active = null)}
	>
		<svg
			viewBox="0 0 {width} {height}"
			{width}
			{height}
			class="block w-full touch-pan-y select-none"
			aria-hidden="true"
			onpointermove={onMove}
			onpointerdown={onMove}
			onpointerleave={() => (active = null)}
		>
			{#each yTicks as t (t)}
				<line
					x1={M.left}
					x2={width - M.right}
					y1={y(t)}
					y2={y(t)}
					stroke="var(--color-chart-grid)"
					stroke-width="1"
					stroke-dasharray={t === 0 ? undefined : '2 3'}
				/>
				<text
					x={M.left - 8}
					y={y(t)}
					dy="0.32em"
					text-anchor="end"
					class="font-mono"
					font-size="10"
					fill="var(--color-chart-tick)">{fmtNum(t, yDigits)}</text
				>
			{/each}
			{#each xTicks as d, i (d)}
				<text
					x={x(d)}
					y={height - 6}
					text-anchor={xTicks.length > 1 && i === 0
						? 'start'
						: xTicks.length > 1 && i === xTicks.length - 1
							? 'end'
							: 'middle'}
					class="font-mono"
					font-size="10"
					fill="var(--color-chart-tick)">{fmtDateShort(d)}</text
				>
			{/each}

			{#if areaPath}
				<path d={areaPath} fill={stroke} opacity="0.08" />
			{/if}
			{#if mean !== null}
				<line
					x1={M.left}
					x2={width - M.right}
					y1={y(mean)}
					y2={y(mean)}
					stroke="var(--color-chart-tick)"
					stroke-width="1"
					stroke-dasharray="4 4"
					opacity="0.7"
				/>
			{/if}
			<path
				d={linePath}
				fill="none"
				{stroke}
				stroke-width="2"
				stroke-linejoin="round"
				stroke-linecap="round"
			/>
			{#if values.length === 1}
				{@const only = points.find((p) => p.value !== null)!}
				<circle cx={x(only.day)} cy={y(only.value!)} r="4" fill={stroke} />
			{/if}

			{#if tip && tip.value !== null}
				<line
					x1={x(tip.day)}
					x2={x(tip.day)}
					y1={M.top}
					y2={M.top + innerH}
					stroke="var(--color-chart-tick)"
					stroke-width="1"
				/>
				<circle
					cx={x(tip.day)}
					cy={y(tip.value)}
					r="4.5"
					fill={stroke}
					stroke="var(--color-panel)"
					stroke-width="2"
				/>
			{/if}
		</svg>

		<div aria-live="polite" class="sr-only">
			{#if tip}{fmtDate(tip.day)}: {fmtNum(tip.value, digits)} {unit}{/if}
		</div>
		{#if tip && tip.value !== null}
			<div
				class="pointer-events-none absolute top-0 -translate-x-1/2 rounded-sm border border-border-strong bg-panel px-2.5 py-1.5 shadow-sm"
				style:left="{tipLeft}px"
				aria-hidden="true"
			>
				<p class="font-mono text-[10px] tracking-wider text-muted uppercase">
					{fmtDate(tip.day)}
				</p>
				<p class="font-mono text-sm tabular whitespace-nowrap text-primary">
					{fmtNum(tip.value, digits)} <span class="text-xs text-muted">{unit}</span>
					{#if tip.runs}<span class="text-xs text-muted"> · {tip.runs} runs</span>{/if}
				</p>
			</div>
		{/if}
	</div>

	<details class="group mt-2">
		<summary
			class="cursor-pointer rounded-sm font-mono text-[11px] tracking-wider text-muted uppercase hover:text-primary"
		>
			Data table
		</summary>
		<div class="mt-2 max-h-64 overflow-auto rounded-sm border border-border">
			<table class="data-table font-mono text-xs tabular">
				<caption class="sr-only">{label} by day</caption>
				<thead>
					<tr>
						<th scope="col" class="px-3 py-2 text-nav text-muted">Day (UTC)</th>
						<th scope="col" class="px-3 py-2 text-right text-nav text-muted">{unit}</th>
						<th scope="col" class="px-3 py-2 text-right text-nav text-muted">Runs</th>
					</tr>
				</thead>
				<tbody>
					{#each points as p (p.day)}
						<tr>
							<td class="py-1.5">{p.day}</td>
							<td class="py-1.5 text-right">{fmtNum(p.value, digits)}</td>
							<td class="py-1.5 text-right text-muted">{p.runs ?? '—'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</details>
</figure>
