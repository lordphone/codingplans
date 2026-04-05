import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-benchmarks',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="space-y-8">
      <header class="mb-16">
        <h1 class="text-[3.5rem] font-extrabold tracking-tighter leading-none mb-2 uppercase">Benchmark Explorer</h1>
        <div class="font-mono text-[0.75rem] text-zinc-500 tracking-widest uppercase">PERFORMANCE METRICS & VERIFICATION DATA</div>
      </header>
      <p class="font-mono text-sm text-zinc-600">Benchmark data loading...</p>
    </div>
  `
})
export class BenchmarksComponent {}
