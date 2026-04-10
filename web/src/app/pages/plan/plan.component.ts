import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
  type WritableSignal
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, EMPTY, from, map, switchMap } from 'rxjs';
import { BackToDirectoryLinkComponent } from '../../components/back-to-directory-link/back-to-directory-link.component';
import { CatalogRefreshStripComponent } from '../../components/catalog-refresh-strip/catalog-refresh-strip.component';
import { CatalogStore } from '../../services/catalog-store.service';
import { SupabaseService } from '../../services/supabase.service';
import type {
  PlanPerformanceDayPoint,
  PlanPerformanceModelBlock,
  PlanPerformancePage,
  PlanQuantRunRow
} from './plan.models';

/** Selectable UTC day windows for plan throughput/latency charts (slice of loaded daily buckets). */
export const PLAN_METRIC_WINDOW_OPTIONS = [3, 7, 14, 30, 60] as const;
export type PlanMetricWindowDays = (typeof PLAN_METRIC_WINDOW_OPTIONS)[number];

function rollingWindowStartUtcIso(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString();
}

function slicePlanSeriesByWindowDays(series: PlanPerformanceDayPoint[], days: number): PlanPerformanceDayPoint[] {
  if (series.length === 0) {
    return series;
  }
  const n = Math.min(Math.max(1, days), series.length);
  return series.slice(-n);
}

function filterQuantRunsByWindow(runs: PlanQuantRunRow[], days: number): PlanQuantRunRow[] {
  const since = rollingWindowStartUtcIso(days);
  return runs.filter(r => r.runAtIso >= since);
}

// --- Sparkline geometry (SVG paths for plan metric cards) ---

interface SparklineSegment {
  linePathD: string;
  areaPathD: string;
}

/** One day column along the x-axis (for hover + axis). */
interface MetricChartColumn {
  index: number;
  x: number;
  dayKey: string;
  axisLabel: string;
  value: number | null;
}

interface MetricChartDot {
  index: number;
  x: number;
  y: number;
  value: number;
}

interface MetricChartAxisTick {
  index: number;
  x: number;
  label: string;
}

interface MetricSparklineGeom {
  segments: SparklineSegment[];
  columns: MetricChartColumn[];
  dots: MetricChartDot[];
  axisTicks: MetricChartAxisTick[];
  /** X-axis segment (matches first/last point x; symmetric inset from view edges). */
  axisLineX1: number;
  axisLineX2: number;
  plotBottomY: number;
  yMin: number | null;
  yMax: number | null;
  hasData: boolean;
  avgValue: number | null;
}

/** Wider viewBox so daily points spread out; keeps curves from looking overly steep. */
const SPARK_W = 400;
/** ViewBox height: plot + bottom time axis strip */
const SPARK_H = 118;
const SPARK_PAD_L = 6;
const SPARK_PAD_R = 6;
const SPARK_PAD_T = 8;
/** Space below the plot for the x-axis line + date labels */
const SPARK_AXIS_STRIP = 22;
/** Symmetric horizontal inset so axis + points aren’t flush to the frame edges. */
const SPARK_X_GUTTER = 14;

interface SparkPt {
  x: number;
  y: number;
}

function catmullRomToBezierPath(points: SparkPt[]): string {
  if (points.length === 0) {
    return '';
  }
  if (points.length === 1) {
    const p = points[0];
    return `M ${p.x} ${p.y}`;
  }
  let d = `M ${points[0].x} ${points[0].y}`;
  if (points.length === 2) {
    const a = points[0];
    const b = points[1];
    return `${d} L ${b.x} ${b.y}`;
  }
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return d;
}

function areaUnderSparkLine(linePathD: string, first: SparkPt, last: SparkPt, plotBottomY: number): string {
  if (!linePathD) {
    return '';
  }
  return `${linePathD} L ${last.x.toFixed(2)} ${plotBottomY} L ${first.x.toFixed(2)} ${plotBottomY} Z`;
}

function pickAxisTickIndices(n: number): number[] {
  if (n <= 0) {
    return [];
  }
  if (n <= 5) {
    return Array.from({ length: n }, (_, i) => i);
  }
  const k = 5;
  const set = new Set<number>();
  for (let j = 0; j < k; j++) {
    set.add(Math.round((j / (k - 1)) * (n - 1)));
  }
  return [...set].sort((a, b) => a - b);
}

/** `dayKey` is YYYY-MM-DD (UTC bucket). */
function formatUtcDayTooltip(dayKey: string): string {
  const [ys, ms, ds] = dayKey.split('-');
  if (!ys || !ms || !ds) {
    return dayKey;
  }
  const y = Number(ys);
  const m = Number(ms);
  const d = Number(ds);
  if (!y || !m || !d) {
    return dayKey;
  }
  const month = new Date(Date.UTC(y, m - 1, d)).toLocaleString(undefined, { month: 'short', timeZone: 'UTC' });
  return `${month} ${d}, ${y} (UTC)`;
}

function buildMetricSparkline(
  series: PlanPerformanceDayPoint[],
  valueKey: 'avgTps' | 'avgTtftS'
): MetricSparklineGeom {
  const plotBottomY = SPARK_H - SPARK_AXIS_STRIP;
  const axisLineX1 = SPARK_PAD_L + SPARK_X_GUTTER;
  const axisLineX2 = SPARK_W - SPARK_PAD_R - SPARK_X_GUTTER;
  const n = series.length;
  if (n === 0) {
    return {
      segments: [],
      columns: [],
      dots: [],
      axisTicks: [],
      axisLineX1,
      axisLineX2,
      plotBottomY,
      yMin: null,
      yMax: null,
      hasData: false,
      avgValue: null
    };
  }

  const bucketVals = series
    .map(p => p[valueKey])
    .filter((v): v is number => v != null && !Number.isNaN(v));
  if (bucketVals.length === 0) {
    return {
      segments: [],
      columns: [],
      dots: [],
      axisTicks: [],
      axisLineX1,
      axisLineX2,
      plotBottomY,
      yMin: null,
      yMax: null,
      hasData: false,
      avgValue: null
    };
  }

  const avgValue = bucketVals.reduce((s, x) => s + x, 0) / bucketVals.length;

  let yMin = Math.min(...bucketVals);
  let yMax = Math.max(...bucketVals);
  if (yMin === yMax) {
    const pad = yMin === 0 ? 1 : Math.abs(yMin) * 0.08;
    yMin -= pad;
    yMax += pad;
  } else {
    const span = yMax - yMin;
    const pad = span * 0.1;
    yMin -= pad;
    yMax += pad;
  }

  const plotW = SPARK_W - SPARK_PAD_L - SPARK_PAD_R;
  const plotInnerW = Math.max(0, plotW - 2 * SPARK_X_GUTTER);
  const plotH = plotBottomY - SPARK_PAD_T;
  const xAt = (i: number) =>
    axisLineX1 + (n === 1 ? plotInnerW / 2 : (i / (n - 1)) * plotInnerW);
  const normY = (v: number) => {
    const t = (v - yMin) / (yMax - yMin);
    return SPARK_PAD_T + (1 - t) * plotH;
  };

  const columns: MetricChartColumn[] = series.map((p, index) => ({
    index,
    x: xAt(index),
    dayKey: p.dayKey,
    axisLabel: p.label,
    value: p[valueKey] != null && !Number.isNaN(Number(p[valueKey])) ? Number(p[valueKey]) : null
  }));

  const dots: MetricChartDot[] = [];
  for (const c of columns) {
    if (c.value != null) {
      dots.push({ index: c.index, x: c.x, y: normY(c.value), value: c.value });
    }
  }

  const axisTicks: MetricChartAxisTick[] = pickAxisTickIndices(n).map(i => ({
    index: i,
    x: xAt(i),
    label: series[i]?.label ?? ''
  }));

  const segments: SparklineSegment[] = [];
  let run: { i: number; v: number }[] = [];

  const flush = () => {
    if (run.length === 0) {
      return;
    }
    let pts: SparkPt[] = run.map(r => ({ x: xAt(r.i), y: normY(r.v) }));
    if (pts.length === 1) {
      const p = pts[0];
      const dx = Math.min(12, plotInnerW * 0.04);
      pts = [
        { x: Math.max(axisLineX1, p.x - dx / 2), y: p.y },
        { x: Math.min(axisLineX2, p.x + dx / 2), y: p.y }
      ];
    }
    const linePathD = catmullRomToBezierPath(pts);
    const first = pts[0];
    const last = pts[pts.length - 1];
    const areaPathD = areaUnderSparkLine(linePathD, first, last, plotBottomY);
    segments.push({ linePathD, areaPathD });
    run = [];
  };

  for (let i = 0; i < n; i++) {
    const v = series[i][valueKey];
    if (v != null && !Number.isNaN(v)) {
      run.push({ i, v });
    } else {
      flush();
    }
  }
  flush();

  return {
    segments,
    columns,
    dots,
    axisTicks,
    axisLineX1,
    axisLineX2,
    plotBottomY,
    yMin,
    yMax,
    hasData: segments.length > 0,
    avgValue
  };
}

/** Pointer feedback for one metric chart (HTML tooltip + SVG crosshair). */
export interface MetricChartHoverUi {
  columnIndex: number;
  lineX: number;
  anchorLeft: number;
  anchorTop: number;
  dateLine: string;
  valueLine: string;
}

@Component({
  selector: 'app-plan',
  standalone: true,
  imports: [CommonModule, RouterLink, BackToDirectoryLinkComponent, CatalogRefreshStripComponent],
  templateUrl: './plan.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class PlanComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly supabase = inject(SupabaseService);
  readonly catalog = inject(CatalogStore);
  private readonly destroyRef = inject(DestroyRef);

  /** SVG viewBox size (shared by throughput + latency charts). */
  readonly chartViewW = SPARK_W;
  readonly chartViewH = SPARK_H;
  readonly chartPadTop = SPARK_PAD_T;

  readonly tpsChartHover = signal<MetricChartHoverUi | null>(null);
  readonly ttftChartHover = signal<MetricChartHoverUi | null>(null);

  /** For nav “back to provider” while the shell is visible (before page data resolves). */
  readonly providerRouteSlug = toSignal(
    this.route.paramMap.pipe(map(p => p.get('providerId') ?? '')),
    { initialValue: '' }
  );

  readonly metricWindowOptions = PLAN_METRIC_WINDOW_OPTIONS;
  readonly throughputWindowDays = signal<PlanMetricWindowDays>(14);
  readonly latencyWindowDays = signal<PlanMetricWindowDays>(14);

  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly missingParams = signal(false);
  readonly notFound = signal(false);
  readonly page = signal<PlanPerformancePage | null>(null);

  /** Active model tab index (resets when a new plan loads). */
  readonly selectedModelIndex = signal(0);

  readonly selectedModel = computed(() => {
    const p = this.page();
    if (!p || p.models.length === 0) {
      return null;
    }
    const i = Math.min(Math.max(0, this.selectedModelIndex()), p.models.length - 1);
    return p.models[i];
  });

  readonly sparklinesByModel = computed(() => {
    const p = this.page();
    const tpsDays = this.throughputWindowDays();
    const ttftDays = this.latencyWindowDays();
    const mapById = new Map<string, { tps: MetricSparklineGeom; ttft: MetricSparklineGeom }>();
    if (!p) {
      return mapById;
    }
    for (const m of p.models) {
      const tpsSlice = slicePlanSeriesByWindowDays(m.tpsSeries, tpsDays);
      const ttftSlice = slicePlanSeriesByWindowDays(m.ttftSeries, ttftDays);
      mapById.set(m.modelId, {
        tps: buildMetricSparkline(tpsSlice, 'avgTps'),
        ttft: buildMetricSparkline(ttftSlice, 'avgTtftS')
      });
    }
    return mapById;
  });

  constructor() {
    this.route.paramMap
      .pipe(
        map(params => ({
          providerSlug: params.get('providerId') ?? '',
          planSlug: params.get('planId') ?? '',
          modelSlug: (params.get('modelSlug') ?? '').trim()
        })),
        switchMap(({ providerSlug, planSlug, modelSlug }) =>
          from(this.catalog.ensureLoaded()).pipe(
            switchMap(() => {
              if (!providerSlug || !planSlug) {
                this.missingParams.set(true);
                this.notFound.set(false);
                this.page.set(null);
                this.loading.set(false);
                this.loadError.set(null);
                return EMPTY;
              }
              this.missingParams.set(false);

              const cached = this.page();
              if (
                cached &&
                cached.providerSlug === providerSlug &&
                cached.planSlug === planSlug
              ) {
                this.loading.set(false);
                this.loadError.set(null);
                this.syncModelSelectionWithUrl(modelSlug, cached);
                return EMPTY;
              }

              const cachedPage = this.catalog.getPlanPage(providerSlug, planSlug);
              if (cachedPage) {
                this.page.set(cachedPage);
                this.notFound.set(false);
                this.loadError.set(null);
                this.loading.set(false);
                this.syncModelSelectionWithUrl(modelSlug, cachedPage);
                return EMPTY;
              }

              this.loading.set(true);
              this.loadError.set(null);
              return from(this.supabase.fetchPlanPerformancePage(providerSlug, planSlug)).pipe(
                map(data => ({ data, modelSlug } as const)),
                catchError(err => {
                  console.error('Plan page load failed', err);
                  const message =
                    err && typeof err === 'object' && 'message' in err && typeof (err as { message: unknown }).message === 'string'
                      ? (err as { message: string }).message
                      : 'Could not load plan from Supabase.';
                  this.loadError.set(message);
                  this.page.set(null);
                  this.notFound.set(false);
                  this.loading.set(false);
                  return EMPTY;
                })
              );
            })
          )
        ),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(({ data, modelSlug }) => {
        this.loading.set(false);
        if (data === null) {
          this.notFound.set(true);
          this.page.set(null);
          return;
        }
        this.notFound.set(false);
        this.page.set(data);
        this.syncModelSelectionWithUrl(modelSlug, data);
      });
  }

  /**
   * Canonical URLs include `modelSlug`. Three-segment `/directory/:provider/:plan` redirects to the first model.
   */
  private syncModelSelectionWithUrl(modelSlug: string, page: PlanPerformancePage): void {
    if (page.models.length === 0) {
      return;
    }
    if (!modelSlug) {
      const first = page.models[0].modelSlug;
      void this.router.navigate(['/directory', page.providerSlug, page.planSlug, first], { replaceUrl: true });
      return;
    }
    const idx = page.models.findIndex(m => m.modelSlug === modelSlug);
    if (idx === -1) {
      void this.router.navigate(['/directory', page.providerSlug, page.planSlug, page.models[0].modelSlug], {
        replaceUrl: true
      });
      return;
    }
    this.selectedModelIndex.set(idx);
  }

  selectThroughputWindow(days: PlanMetricWindowDays): void {
    this.throughputWindowDays.set(days);
    this.tpsChartHover.set(null);
  }

  selectLatencyWindow(days: PlanMetricWindowDays): void {
    this.latencyWindowDays.set(days);
    this.ttftChartHover.set(null);
  }

  /** Quantization rows follow the throughput card’s window (independent from latency). */
  quantRunsForWindow(model: PlanPerformanceModelBlock): PlanQuantRunRow[] {
    return filterQuantRunsByWindow(model.quantRuns, this.throughputWindowDays());
  }

  selectModelTab(index: number): void {
    const p = this.page();
    if (!p || index < 0 || index >= p.models.length) {
      return;
    }
    this.tpsChartHover.set(null);
    this.ttftChartHover.set(null);
    const m = p.models[index];
    void this.router.navigate(['/directory', p.providerSlug, p.planSlug, m.modelSlug], { replaceUrl: true });
  }

  sparkFor(modelId: string): { tps: MetricSparklineGeom; ttft: MetricSparklineGeom } | undefined {
    return this.sparklinesByModel().get(modelId);
  }

  onTpsChartPointerMove(event: PointerEvent, geom: MetricSparklineGeom): void {
    this.updateMetricChartHover(event, geom, 'tps', this.tpsChartHover);
  }

  onTpsChartPointerLeave(): void {
    this.tpsChartHover.set(null);
  }

  onTtftChartPointerMove(event: PointerEvent, geom: MetricSparklineGeom): void {
    this.updateMetricChartHover(event, geom, 'ttft', this.ttftChartHover);
  }

  onTtftChartPointerLeave(): void {
    this.ttftChartHover.set(null);
  }

  private updateMetricChartHover(
    event: PointerEvent,
    geom: MetricSparklineGeom,
    kind: 'tps' | 'ttft',
    target: WritableSignal<MetricChartHoverUi | null>
  ): void {
    if (!geom.columns.length) {
      target.set(null);
      return;
    }
    const svg = event.currentTarget as SVGSVGElement;
    const ctm = svg.getScreenCTM();
    if (!ctm) {
      return;
    }
    const pt = svg.createSVGPoint();
    pt.x = event.clientX;
    pt.y = event.clientY;
    const local = pt.matrixTransform(ctm.inverse());
    const xSvg = local.x;

    let bestIdx = 0;
    let bestDist = Infinity;
    for (let i = 0; i < geom.columns.length; i++) {
      const dist = Math.abs(geom.columns[i].x - xSvg);
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }

    const col = geom.columns[bestIdx];
    const valueLine =
      kind === 'tps'
        ? col.value == null
          ? 'No throughput sample'
          : this.formatAvgTokPerS(col.value)
        : col.value == null
          ? 'No latency sample'
          : this.formatTtft(col.value);

    const wrap = svg.parentElement;
    if (!wrap) {
      return;
    }
    const wrect = wrap.getBoundingClientRect();
    const tipW = 148;
    const tipH = 40;
    let anchorLeft = event.clientX - wrect.left + 12;
    let anchorTop = event.clientY - wrect.top - 52;
    anchorLeft = Math.min(Math.max(4, anchorLeft), Math.max(4, wrect.width - tipW - 4));
    anchorTop = Math.min(Math.max(4, anchorTop), Math.max(4, wrect.height - tipH - 4));

    target.set({
      columnIndex: bestIdx,
      lineX: col.x,
      anchorLeft,
      anchorTop,
      dateLine: formatUtcDayTooltip(col.dayKey),
      valueLine
    });
  }

  formatAvgTokPerS(avg: number | null): string {
    if (avg == null || Number.isNaN(avg)) {
      return '—';
    }
    return `${Math.round(avg)} tok/s`;
  }

  formatTtft(seconds: number | null): string {
    if (seconds == null || Number.isNaN(seconds)) {
      return '—';
    }
    if (seconds < 1) {
      return `${Math.round(seconds * 1000)} ms`;
    }
    return `${seconds.toFixed(2)} s`;
  }

  showsQuantizationLossNotice(label: string, status: 'scam' | 'verified'): boolean {
    if (status !== 'scam') {
      return false;
    }
    const q = label.toLowerCase();
    return q.includes('scam') || /\breset\b/.test(q);
  }
}
