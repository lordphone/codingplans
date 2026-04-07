import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

interface PlanDetail {
  id: string;
  name: string;
  tierId: string;
  price: string;
  period: string;
  modelTarget: string;
  quantization: string;
  quantizationColor: 'tertiary' | 'secondary';
  tps: string;
  notice?: string;
}

@Component({
  selector: 'app-provider',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <!-- Breadcrumb -->
    <nav class="mb-8">
      <a routerLink="/directory" class="font-mono text-[11px] uppercase tracking-wider text-zinc-500 hover:text-emerald-700 transition-colors">
        ← BACK TO DIRECTORY
      </a>
    </nav>

    <!-- Header Editorial Layout -->
    <div class="mb-16">
      <h1 class="text-[3.5rem] font-bold leading-tight tracking-tighter text-on-surface uppercase mb-2">
        {{ providerName }}
      </h1>
      <p class="font-mono text-[0.75rem] text-zinc-500 tracking-wider">LAST UPDATE: {{ lastUpdated }}</p>
    </div>

    <!-- Tier comparison: one row, equal-width columns; scroll horizontally if the viewport is too narrow -->
    <div class="w-full overflow-x-auto">
      <div
        class="grid min-w-full border border-zinc-300"
        [style.grid-template-columns]="'repeat(' + plans.length + ', minmax(12rem, 1fr))'">
      @for (plan of plans; track plan.id; let i = $index) {
        <div
          class="min-w-0 border-zinc-300 p-8"
          [class.border-l]="i > 0"
          [class.bg-surface]="i % 2 === 0"
          [class.bg-white]="i % 2 === 1">
          <!-- Plan Header -->
          <div class="flex justify-between items-start mb-12">
            <div>
              <a [routerLink]="['/directory', providerId, plan.id]" 
                 class="text-2xl font-bold tracking-tight mb-1 hover:text-emerald-700 transition-colors">
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
                    <div class="w-2.5 h-2.5" [class.bg-red-700]="plan.quantizationColor === 'tertiary'" [class.bg-emerald-600]="plan.quantizationColor === 'secondary'"></div>
                    <span class="font-mono text-[0.75rem] font-bold uppercase" [class.text-red-700]="plan.quantizationColor === 'tertiary'" [class.text-emerald-600]="plan.quantizationColor === 'secondary'">
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
            <div class="p-4" [class.bg-zinc-100]="i % 2 === 0" [class.bg-white.border.border-zinc-300]="i % 2 === 1">
              <p class="font-mono text-[0.7rem] text-zinc-600 uppercase leading-relaxed">
                {{ plan.notice }}
              </p>
            </div>
          </div>
        </div>
      }
      </div>
    </div>

    <!-- Audit Verification Box -->
    <div class="mt-16 border border-zinc-300 p-8 flex flex-col md:flex-row justify-between items-start gap-8">
      <div class="max-w-xl">
        <h4 class="font-mono text-[0.75rem] font-bold mb-4 flex items-center gap-2 uppercase">
          <span class="material-icons text-[14px]">verified_user</span>
          AUDIT VERIFICATION CERTIFICATE
        </h4>
        <p class="font-mono text-[0.7rem] text-zinc-600 uppercase leading-loose">
          The data presented above has been mathematically verified against {{ providerName }} API endpoints. 
          Performance metrics represent sustained throughput under standard load conditions. 
          No synthetic interpolation was used in these findings.
        </p>
      </div>
      <div class="flex flex-col gap-2 min-w-[200px]">
        <div class="flex justify-between border-b border-zinc-300 pb-1">
          <span class="font-mono text-[0.65rem] text-zinc-500 uppercase">STATUS</span>
          <span class="font-mono text-[0.65rem] font-bold text-emerald-600 uppercase">VERIFIED PASS</span>
        </div>
        <div class="flex justify-between border-b border-zinc-300 pb-1">
          <span class="font-mono text-[0.65rem] text-zinc-500 uppercase">LATENCY AUDIT</span>
          <span class="font-mono text-[0.65rem] font-bold text-emerald-600 uppercase">OK</span>
        </div>
        <div class="flex justify-between border-b border-zinc-300 pb-1">
          <span class="font-mono text-[0.65rem] text-zinc-500 uppercase">TOKEN RELIABILITY</span>
          <span class="font-mono text-[0.65rem] font-bold text-emerald-600 uppercase">99.98%</span>
        </div>
      </div>
    </div>
  `
})
export class ProviderComponent {
  @Input() providerId: string = '';

  providerName = 'Alibaba Cloud';
  lastUpdated = '2024-10-24 14:30:01 UTC';

  plans: PlanDetail[] = [
    {
      id: 'lite',
      name: 'LITE ENTRY',
      tierId: 'ACMS LITE 001',
      price: '$10',
      period: '/ MO',
      modelTarget: 'KIMI 8B INSTRUCT',
      quantization: 'INT4',
      quantizationColor: 'tertiary',
      tps: '18.5',
      notice: 'NOTICE: LITE tier implements aggressive quantization to maintain cost efficiency. Expect precision degradation in complex reasoning tasks.'
    },
    {
      id: 'standard',
      name: 'STANDARD (TEST)',
      tierId: 'ACMS STD 200',
      price: '$25',
      period: '/ MO',
      modelTarget: 'KIMI 8B INSTRUCT',
      quantization: 'INT8',
      quantizationColor: 'tertiary',
      tps: '52.0',
      notice: 'TEST TIER: Placeholder middle plan to verify single-row layout with three columns.'
    },
    {
      id: 'pro',
      name: 'PRO ELITE',
      tierId: 'ACMS PRO 500',
      price: '$50',
      period: '/ MO',
      modelTarget: 'KIMI 8B INSTRUCT',
      quantization: 'FP16',
      quantizationColor: 'secondary',
      tps: '142.0',
      notice: 'TECHNICAL SUMMARY: PRO tier provides full precision floating point support and significantly higher throughput limits for production-ready reliability.'
    }
  ];
}
