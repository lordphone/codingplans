import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { SupabaseService } from '../../services/supabase.service';
import type { DisplayProvider } from '../../types/database.types';

@Component({
  selector: 'app-directory',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  template: `
    <!-- Editorial Header -->
    <header class="mb-8">
      <h1 class="text-[3.5rem] font-extrabold tracking-tighter leading-none mb-2 uppercase">Plan Comparison Log</h1>
      <div class="font-mono text-[0.75rem] text-zinc-500 tracking-widest uppercase">SYST REPORT :: COMPREHENSIVE LLM PRICING MATRIX</div>
    </header>

    @if (loading) {
      <p class="font-mono text-sm text-zinc-500 uppercase">Loading directory from database…</p>
    } @else if (loadError) {
      <div class="border border-red-200 bg-red-50 p-4 font-mono text-sm text-red-800">
        {{ loadError }}
      </div>
    } @else {
      <!-- Search Bar -->
      <div class="mb-12">
        <div class="relative">
          <input
            type="text"
            [(ngModel)]="searchQuery"
            (input)="onSearch()"
            placeholder="Search providers, plans, models..."
            class="w-full bg-white border border-zinc-300 px-4 py-3 font-mono text-sm outline-none focus:border-emerald-600 transition-colors"
          />
          <span class="absolute right-4 top-1/2 -translate-y-1/2 font-mono text-[10px] text-zinc-400 uppercase">
            {{ filteredCount }} RESULTS
          </span>
        </div>
      </div>

      <!-- Data Ledger -->
      <div class="w-full space-y-12">
        @for (provider of filteredProviders; track provider.id) {
          <section class="space-y-4">
            <!-- Provider Header -->
            <div class="flex items-end justify-between border-b border-zinc-200 pb-2">
              <a
                [routerLink]="['/directory', provider.id]"
                class="text-xl font-bold tracking-tight uppercase hover:text-emerald-700 transition-colors"
              >
                {{ provider.name }}
              </a>
              <span class="font-mono text-[10px] text-zinc-400">PROVIDER SLUG: {{ provider.id }}</span>
            </div>

            <!-- Plans Grid -->
            <div class="grid grid-cols-12 gap-1 bg-surface-container-low p-1">
              <!-- Table Header -->
              <div class="col-span-3 bg-surface-container-highest px-4 py-2 font-mono text-[9px] text-zinc-500">TIER</div>
              <div class="col-span-3 bg-surface-container-highest px-4 py-2 font-mono text-[9px] text-zinc-500">
                MODEL ARCHITECTURE
              </div>
              <div class="col-span-2 bg-surface-container-highest px-4 py-2 font-mono text-[9px] text-zinc-500">
                SPEED (TPS)
              </div>
              <div class="col-span-2 bg-surface-container-highest px-4 py-2 font-mono text-[9px] text-zinc-500 text-right">
                QUANTIZATION
              </div>
              <div class="col-span-2 bg-surface-container-highest px-4 py-2 font-mono text-[9px] text-zinc-500 text-right">
                COST UNIT
              </div>

              <!-- Plan Rows -->
              @for (plan of provider.plans; track plan.id; let last = $last) {
                <div class="col-span-3 bg-white px-4 py-6 flex flex-col justify-center" [class.border-t.border-zinc-50]="!$first">
                  <a
                    [routerLink]="['/directory', provider.id, plan.id]"
                    class="font-bold text-sm tracking-tight hover:text-emerald-700 transition-colors"
                  >
                    {{ plan.name }}
                  </a>
                  <span class="font-mono text-[10px] text-zinc-400 uppercase">{{ plan.subtitle }}</span>
                </div>
                <div class="col-span-3 bg-white px-4 py-6 flex flex-col justify-center" [class.border-t.border-zinc-50]="!$first">
                  <span class="font-mono text-xs">{{ plan.models }}</span>
                </div>
                <div class="col-span-2 bg-white px-4 py-6 flex items-center" [class.border-t.border-zinc-50]="!$first">
                  <div class="w-full bg-zinc-100 h-2">
                    <div class="bg-black h-full" [style.width.%]="plan.tpsPercent"></div>
                  </div>
                  <span class="font-mono text-[10px] ml-2">{{ plan.tps }}</span>
                </div>
                <div
                  class="col-span-2 bg-white px-4 py-6 flex flex-col justify-center items-end"
                  [class.border-t.border-zinc-50]="!$first"
                >
                  <div class="flex items-center gap-2">
                    <span class="font-mono text-[10px]">{{ plan.quantization }}</span>
                    <div
                      class="w-2.5 h-2.5"
                      [class.bg-tertiary]="plan.quantizationStatus === 'scam'"
                      [class.bg-secondary]="plan.quantizationStatus === 'verified'"
                    ></div>
                  </div>
                  <span class="font-mono text-[8px] text-zinc-400 mt-1 uppercase">
                    {{ plan.quantizationStatus === 'scam' ? 'Loss Detected' : 'Verified Zero Loss' }}
                  </span>
                </div>
                <div
                  class="col-span-2 bg-white px-4 py-6 flex flex-col justify-center items-end"
                  [class.border-t.border-zinc-50]="!$first"
                >
                  <span class="font-mono text-sm font-bold">{{ plan.price }}</span>
                  <span class="font-mono text-[8px] text-zinc-400 uppercase">{{ plan.period }}</span>
                </div>
              }
            </div>
          </section>
        } @empty {
          <p class="font-mono text-sm text-zinc-500 uppercase">No providers match this search.</p>
        }

        <!-- Legend -->
        <div class="flex justify-start gap-12 mt-8 pt-8 border-t border-zinc-100">
          <div class="flex items-center gap-3">
            <div class="w-4 h-4 bg-secondary"></div>
            <span class="font-mono text-[9px] uppercase tracking-widest text-zinc-500">FP16 FULL FIDELITY</span>
          </div>
          <div class="flex items-center gap-3">
            <div class="w-4 h-4 bg-tertiary"></div>
            <span class="font-mono text-[9px] uppercase tracking-widest text-zinc-500">INT4 PRECISION DETECTED</span>
          </div>
        </div>
      </div>
    }
  `
})
export class DirectoryComponent implements OnInit {
  private supabase = inject(SupabaseService);

  searchQuery = '';
  providers: DisplayProvider[] = [];
  loading = true;
  loadError: string | null = null;

  async ngOnInit(): Promise<void> {
    try {
      const [rawProviders, runs] = await Promise.all([
        this.supabase.getProvidersWithPlans(),
        this.supabase.getBenchmarkRunsOrderedSafe()
      ]);
      const benchMap = this.supabase.latestBenchmarkByPlanModel(runs);
      this.providers = this.supabase.buildDirectoryView(rawProviders, benchMap);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.loadError =
        'Could not load directory from Supabase. Check RLS, table names, and foreign keys (providers → plans → plan_models → models). ' +
        msg;
    } finally {
      this.loading = false;
    }
  }

  get filteredProviders(): DisplayProvider[] {
    if (!this.searchQuery.trim()) {
      return this.providers;
    }

    const query = this.searchQuery.toLowerCase();
    return this.providers
      .map(provider => {
        const filteredPlans = provider.plans.filter(
          plan =>
            plan.name.toLowerCase().includes(query) ||
            plan.models.toLowerCase().includes(query) ||
            provider.name.toLowerCase().includes(query)
        );
        return { ...provider, plans: filteredPlans };
      })
      .filter(
        provider => provider.plans.length > 0 || provider.name.toLowerCase().includes(query)
      );
  }

  get filteredCount(): number {
    return this.filteredProviders.reduce((sum, p) => sum + p.plans.length, 0);
  }

  onSearch(): void {
    // Reactive filtering happens via getters
  }
}
