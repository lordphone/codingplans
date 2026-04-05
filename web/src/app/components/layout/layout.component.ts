import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <div class="min-h-screen flex flex-col">
      <!-- TopNavBar -->
      <nav class="fixed top-0 left-0 right-0 z-50 flex justify-between items-center w-full px-12 h-16 bg-white border-b border-zinc-200">
        <div class="flex items-center gap-4">
          <a routerLink="/" class="text-xl font-light tracking-[0.5em] text-zinc-900 uppercase">
            CODING PLAN COMPARISON
          </a>
          <span class="font-mono text-[9px] text-zinc-400 uppercase">V 1.0.4</span>
        </div>
        <div class="flex gap-12">
          <a routerLink="/directory" 
             routerLinkActive="border-b border-zinc-900 text-zinc-900"
             class="font-['Inter'] uppercase tracking-[0.2em] text-[10px] font-bold text-zinc-400 pb-1 hover:text-zinc-900 transition-colors">
            DIRECTORY
          </a>
          <a routerLink="/benchmarks"
             routerLinkActive="border-b border-zinc-900 text-zinc-900"
             class="font-['Inter'] uppercase tracking-[0.2em] text-[10px] font-bold text-zinc-400 pb-1 hover:text-zinc-900 transition-colors">
            BENCHMARKS
          </a>
        </div>
      </nav>

      <div class="flex flex-1 pt-16">
        <!-- SideNavBar (Filters) -->
        <aside class="fixed left-0 top-16 w-64 h-full flex flex-col p-8 gap-6 bg-zinc-50 border-r border-zinc-200">
          <div class="flex flex-col gap-1">
            <span class="font-mono text-[11px] uppercase tracking-wider text-emerald-700 font-bold">FILTERS</span>
          </div>
          <nav class="flex flex-col gap-4">
            <a routerLink="/models"
               routerLinkActive="text-emerald-700"
               class="font-mono text-[11px] uppercase tracking-wider text-zinc-500 hover:bg-zinc-200 p-1 transition-colors">
              MODELS
            </a>
            <a routerLink="/directory"
               routerLinkActive="text-emerald-700"
               class="font-mono text-[11px] uppercase tracking-wider text-zinc-500 hover:bg-zinc-200 p-1 transition-colors">
              PROVIDERS
            </a>
            <a routerLink="/directory" [queryParams]="{filter: 'speed'}"
               class="font-mono text-[11px] uppercase tracking-wider text-zinc-500 hover:bg-zinc-200 p-1 transition-colors">
              SPEED
            </a>
            <a routerLink="/directory" [queryParams]="{filter: 'quantization'}"
               class="font-mono text-[11px] uppercase tracking-wider text-zinc-500 hover:bg-zinc-200 p-1 transition-colors">
              QUANTIZATION
            </a>
          </nav>
        </aside>

        <!-- Main Content -->
        <main class="ml-64 flex-1 p-12 bg-surface">
          <router-outlet></router-outlet>
        </main>
      </div>
    </div>
  `
})
export class LayoutComponent {}
