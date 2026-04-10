import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
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

interface MetricSparklineGeom {
  segments: SparklineSegment[];
  yMin: number | null;
  yMax: number | null;
  hasData: boolean;
  avgValue: number | null;
}

const SPARK_W = 320;
const SPARK_H = 120;
const SPARK_PAD_L = 4;
const SPARK_PAD_R = 4;
const SPARK_PAD_T = 12;
const SPARK_PAD_B = 8;
const SPARK_BOTTOM_Y = SPARK_H - SPARK_PAD_B;

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

function areaUnderSparkLine(linePathD: string, first: SparkPt, last: SparkPt): string {
  if (!linePathD) {
    return '';
  }
  return `${linePathD} L ${last.x.toFixed(2)} ${SPARK_BOTTOM_Y} L ${first.x.toFixed(2)} ${SPARK_BOTTOM_Y} Z`;
}

function buildMetricSparkline(
  series: PlanPerformanceDayPoint[],
  valueKey: 'avgTps' | 'avgTtftS'
): MetricSparklineGeom {
  const n = series.length;
  if (n === 0) {
    return { segments: [], yMin: null, yMax: null, hasData: false, avgValue: null };
  }

  const bucketVals = series
    .map(p => p[valueKey])
    .filter((v): v is number => v != null && !Number.isNaN(v));
  if (bucketVals.length === 0) {
    return { segments: [], yMin: null, yMax: null, hasData: false, avgValue: null };
  }

  const avgValue = bucketVals.reduce((s, x) => s + x, 0) / bucketVals.length;

  let yMin = Math.min(...bucketVals);
  let yMax = Math.max(...bucketVals);
  if (yMin === yMax) {
    const pad = yMin === 0 ? 1 : Math.abs(yMin) * 0.06;
    yMin -= pad;
    yMax += pad;
  }

  const plotW = SPARK_W - SPARK_PAD_L - SPARK_PAD_R;
  const plotH = SPARK_H - SPARK_PAD_T - SPARK_PAD_B;
  const xAt = (i: number) => SPARK_PAD_L + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const normY = (v: number) => {
    const t = (v - yMin) / (yMax - yMin);
    return SPARK_PAD_T + (1 - t) * plotH;
  };

  const segments: SparklineSegment[] = [];
  let run: { i: number; v: number }[] = [];

  const flush = () => {
    if (run.length === 0) {
      return;
    }
    let pts: SparkPt[] = run.map(r => ({ x: xAt(r.i), y: normY(r.v) }));
    if (pts.length === 1) {
      const p = pts[0];
      const dx = Math.min(12, plotW * 0.04);
      pts = [
        { x: Math.max(SPARK_PAD_L, p.x - dx / 2), y: p.y },
        { x: Math.min(SPARK_W - SPARK_PAD_R, p.x + dx / 2), y: p.y }
      ];
    }
    const linePathD = catmullRomToBezierPath(pts);
    const first = pts[0];
    const last = pts[pts.length - 1];
    const areaPathD = areaUnderSparkLine(linePathD, first, last);
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
    yMin,
    yMax,
    hasData: segments.length > 0,
    avgValue
  };
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

  /** For nav “back to provider” while the shell is visible (before page data resolves). */
  readonly providerRouteSlug = toSignal(
    this.route.paramMap.pipe(map(p => p.get('providerId') ?? '')),
    { initialValue: '' }
  );

  readonly metricWindowOptions = PLAN_METRIC_WINDOW_OPTIONS;
  readonly selectedMetricWindowDays = signal<PlanMetricWindowDays>(14);

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
    const days = this.selectedMetricWindowDays();
    const mapById = new Map<string, { tps: MetricSparklineGeom; ttft: MetricSparklineGeom }>();
    if (!p) {
      return mapById;
    }
    for (const m of p.models) {
      const slice = slicePlanSeriesByWindowDays(m.tpsSeries, days);
      mapById.set(m.modelId, {
        tps: buildMetricSparkline(slice, 'avgTps'),
        ttft: buildMetricSparkline(slice, 'avgTtftS')
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

  selectMetricWindow(days: PlanMetricWindowDays): void {
    this.selectedMetricWindowDays.set(days);
  }

  quantRunsForWindow(model: PlanPerformanceModelBlock): PlanQuantRunRow[] {
    return filterQuantRunsByWindow(model.quantRuns, this.selectedMetricWindowDays());
  }

  selectModelTab(index: number): void {
    const p = this.page();
    if (!p || index < 0 || index >= p.models.length) {
      return;
    }
    const m = p.models[index];
    void this.router.navigate(['/directory', p.providerSlug, p.planSlug, m.modelSlug], { replaceUrl: true });
  }

  sparkFor(modelId: string): { tps: MetricSparklineGeom; ttft: MetricSparklineGeom } | undefined {
    return this.sparklinesByModel().get(modelId);
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
