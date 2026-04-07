import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, EMPTY, from, map, switchMap } from 'rxjs';
import { SupabaseService } from '../../services/supabase.service';
import type { PlanPerformancePage } from './plan.models';
import { buildMetricSparkline, type MetricSparklineGeom } from './plan-sparkline';

const WINDOW_DAYS = 30;

@Component({
  selector: 'app-plan',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './plan.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class PlanComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly supabase = inject(SupabaseService);
  private readonly destroyRef = inject(DestroyRef);

  readonly windowDays = WINDOW_DAYS;

  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly missingParams = signal(false);
  readonly notFound = signal(false);
  readonly page = signal<PlanPerformancePage | null>(null);

  readonly sparklinesByModel = computed(() => {
    const p = this.page();
    const mapById = new Map<string, { tps: MetricSparklineGeom; ttft: MetricSparklineGeom }>();
    if (!p) {
      return mapById;
    }
    for (const m of p.models) {
      mapById.set(m.modelId, {
        tps: buildMetricSparkline(m.tpsSeries, 'avgTps'),
        ttft: buildMetricSparkline(m.ttftSeries, 'avgTtftS')
      });
    }
    return mapById;
  });

  constructor() {
    this.route.paramMap
      .pipe(
        map(params => ({
          providerSlug: params.get('providerId') ?? '',
          planSlug: params.get('planId') ?? ''
        })),
        switchMap(({ providerSlug, planSlug }) => {
          if (!providerSlug || !planSlug) {
            this.missingParams.set(true);
            this.notFound.set(false);
            this.page.set(null);
            this.loading.set(false);
            this.loadError.set(null);
            return EMPTY;
          }
          this.missingParams.set(false);
          this.loading.set(true);
          this.loadError.set(null);
          return from(this.supabase.fetchPlanPerformancePage(providerSlug, planSlug)).pipe(
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
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(data => {
        this.loading.set(false);
        if (data === null) {
          this.notFound.set(true);
          this.page.set(null);
        } else {
          this.notFound.set(false);
          this.page.set(data);
        }
      });
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
