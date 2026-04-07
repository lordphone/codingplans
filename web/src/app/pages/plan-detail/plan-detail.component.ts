import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs/operators';

@Component({
  selector: 'app-plan-detail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <nav class="mb-8 flex flex-wrap gap-x-4 gap-y-2 font-mono text-[11px] uppercase tracking-wider text-zinc-500">
      <a routerLink="/directory" class="hover:text-emerald-700 transition-colors">Directory</a>
      <span aria-hidden="true">/</span>
      <a [routerLink]="['/directory', providerId()]" class="hover:text-emerald-700 transition-colors">
        {{ providerId() || '…' }}
      </a>
    </nav>

    <header class="mb-16 space-y-2">
      <h1 class="text-[3.5rem] font-extrabold tracking-tighter leading-none uppercase">Plan</h1>
      <p class="font-mono text-[0.75rem] text-zinc-500 tracking-widest uppercase">
        {{ planId() || '…' }} — detail view coming soon
      </p>
    </header>

    <p class="font-mono text-sm text-zinc-600 max-w-prose">
      This page will show models, pricing, and benchmarks for this tier. For now, use the provider audit report for a
      side-by-side comparison.
    </p>
  `
})
export class PlanDetailComponent {
  private readonly route = inject(ActivatedRoute);

  readonly providerId = toSignal(
    this.route.paramMap.pipe(map(p => p.get('providerId') ?? '')),
    { initialValue: '' }
  );

  readonly planId = toSignal(this.route.paramMap.pipe(map(p => p.get('planId') ?? '')), { initialValue: '' });
}
