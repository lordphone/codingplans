import { Component, inject, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { SupabaseService } from '../../services/supabase.service';
import type { PlanDetailView } from '../../types/database.types';

@Component({
  selector: 'app-provider-detail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <!-- Breadcrumb -->
    <nav class="mb-8">
      <a
        routerLink="/directory"
        class="font-mono text-[11px] uppercase tracking-wider text-zinc-500 hover:text-emerald-700 transition-colors"
      >
        ← BACK TO DIRECTORY
      </a>
    </nav>

    @if (loading) {
      <p class="font-mono text-sm text-zinc-500 uppercase">Loading provider…</p>
    } @else if (loadError) {
      <div class="border border-red-200 bg-red-50 p-4 font-mono text-sm text-red-800">
        {{ loadError }}
      </div>
    } @else if (!providerName) {
      <p class="font-mono text-sm text-zinc-500 uppercase">Provider not found.</p>
    } @else {
      <!-- Header Editorial Layout -->
      <div class="mb-16">
        <h1 class="text-[3.5rem] font-bold leading-tight tracking-tighter text-on-surface uppercase mb-2">
          Audit Report:<br />{{ providerName }}
        </h1>
        <p class="font-mono text-[0.75rem] text-zinc-500 tracking-wider">TIMESTAMP: {{ timestamp }}</p>
      </div>

      @if (plans.length === 0) {
        <p class="font-mono text-sm text-zinc-500 uppercase">No active plans for this provider.</p>
      } @else {
        <!-- Tier Comparison Grid -->
        <div class="grid grid-cols-2 gap-px bg-zinc-300">
          @for (plan of plans; track plan.id) {
            <div class="p-8" [class.bg-surface]="!plan.isPro" [class.bg-white]="plan.isPro">
              <!-- Plan Header -->
              <div class="flex justify-between items-start mb-12">
                <div>
                  <a
                    [routerLink]="['/directory', providerSlug, plan.id]"
                    class="text-2xl font-bold tracking-tight mb-1 hover:text-emerald-700 transition-colors"
                  >
                    {{ plan.name }}
                  </a>
                  <p class="font-mono text-[0.75rem] text-zinc-500 uppercase">TIER ID: {{ plan.tierId }}</p>
                </div>
                <div class="text-right">
                  <span class="text-3xl font-light">{{ plan.price }}</span>
                  <span class="font-mono text-[0.65rem] block text-zinc-500 uppercase">USD {{ plan.period }}</span>
                </div>
              </div>

              <!-- Specifications -->
              <div class="space-y-8">
                <section>
                  <h3 class="text-[0.65rem] font-bold tracking-[0.2em] text-zinc-500 uppercase mb-4">SPECIFICATIONS</h3>
                  <div class="space-y-3">
                    <div class="flex justify-between items-center border-b border-zinc-200 pb-2">
                      <span class="font-mono text-[0.75rem] uppercase">MODEL TARGET</span>
                      <span class="font-mono text-[0.75rem] font-bold uppercase">{{ plan.modelTarget }}</span>
                    </div>
                    <div class="flex justify-between items-center border-b border-zinc-200 pb-2">
                      <span class="font-mono text-[0.75rem] uppercase">QUANTIZATION</span>
                      <div class="flex items-center gap-2">
                        <div
                          class="w-2.5 h-2.5"
                          [class.bg-red-700]="plan.quantizationColor === 'tertiary'"
                          [class.bg-emerald-600]="plan.quantizationColor === 'secondary'"
                        ></div>
                        <span
                          class="font-mono text-[0.75rem] font-bold uppercase"
                          [class.text-red-700]="plan.quantizationColor === 'tertiary'"
                          [class.text-emerald-600]="plan.quantizationColor === 'secondary'"
                        >
                          {{ plan.quantization }}
                        </span>
                      </div>
                    </div>
                    <div class="flex justify-between items-center border-b border-zinc-200 pb-2">
                      <span class="font-mono text-[0.75rem] uppercase">TPS LIMIT</span>
                      <span class="font-mono text-[0.75rem] font-bold uppercase">{{ plan.tps }}</span>
                    </div>
                  </div>
                </section>

                <!-- Notice Box -->
                <div class="p-4" [class.bg-zinc-100]="!plan.isPro" [class.bg-white.border.border-zinc-300]="plan.isPro">
                  <p class="font-mono text-[0.7rem] text-zinc-600 uppercase leading-relaxed">
                    {{ plan.notice }}
                  </p>
                </div>
              </div>
            </div>
          }
        </div>
      }

      <!-- Audit Verification Box -->
      <div class="mt-16 border border-zinc-300 p-8 flex flex-col md:flex-row justify-between items-start gap-8">
        <div class="max-w-xl">
          <h4 class="font-mono text-[0.75rem] font-bold mb-4 flex items-center gap-2 uppercase">
            <span class="material-icons text-[14px]">verified_user</span>
            AUDIT VERIFICATION CERTIFICATE
          </h4>
          <p class="font-mono text-[0.7rem] text-zinc-600 uppercase leading-loose">
            The data presented above is sourced from the public directory in Supabase. When benchmark runs exist, metrics
            reflect the latest recorded run per plan and model. Quantization labels follow provider-reported or measured
            values.
          </p>
        </div>
        <div class="flex flex-col gap-2 min-w-[200px]">
          <div class="flex justify-between border-b border-zinc-300 pb-1">
            <span class="font-mono text-[0.65rem] text-zinc-500 uppercase">STATUS</span>
            <span class="font-mono text-[0.65rem] font-bold text-emerald-600 uppercase">LOADED</span>
          </div>
          <div class="flex justify-between border-b border-zinc-300 pb-1">
            <span class="font-mono text-[0.65rem] text-zinc-500 uppercase">SOURCE</span>
            <span class="font-mono text-[0.65rem] font-bold text-emerald-600 uppercase">SUPABASE</span>
          </div>
        </div>
      </div>
    }
  `
})
export class ProviderDetailComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private supabase = inject(SupabaseService);
  private sub?: Subscription;

  providerSlug = '';
  providerName = '';
  timestamp = '';
  plans: PlanDetailView[] = [];
  loading = true;
  loadError: string | null = null;

  ngOnInit(): void {
    this.sub = this.route.paramMap.subscribe(params => {
      const slug = params.get('providerId') ?? '';
      const planSlug = params.get('planId');
      void this.loadProvider(slug, planSlug);
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  private async loadProvider(slug: string, planSlug: string | null): Promise<void> {
    this.loading = true;
    this.loadError = null;
    this.providerSlug = slug;

    if (!slug) {
      this.providerName = '';
      this.plans = [];
      this.timestamp = '';
      this.loading = false;
      return;
    }

    try {
      const [row, runs] = await Promise.all([
        this.supabase.getProviderBySlug(slug),
        this.supabase.getBenchmarkRunsOrderedSafe()
      ]);
      const benchMap = this.supabase.latestBenchmarkByPlanModel(runs);

      if (!row) {
        this.providerName = '';
        this.plans = [];
        this.timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
        this.loading = false;
        return;
      }

      this.providerName = row.name;
      this.timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
      let allPlans = this.supabase.plansToDetailViews(row.plans ?? [], benchMap);
      if (planSlug) {
        allPlans = allPlans.filter(p => p.id === planSlug);
      }
      this.plans = allPlans;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.loadError =
        'Could not load provider from Supabase. Check slug, RLS, and nested relations. ' + msg;
      this.providerName = '';
      this.plans = [];
      this.timestamp = '';
    } finally {
      this.loading = false;
    }
  }
}
