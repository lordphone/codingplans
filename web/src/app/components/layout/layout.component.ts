import { Component, inject, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { APP_VERSION } from '../../version';
import { CatalogStore } from '../../services/catalog-store.service';

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
          <span class="font-mono text-[9px] text-zinc-400 uppercase">v{{ appVersion }}</span>
        </div>
        <div class="flex gap-12">
          <a routerLink="/directory"
             routerLinkActive="border-b border-zinc-900 text-zinc-900"
             [routerLinkActiveOptions]="{ exact: true }"
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
        <main class="flex-1 p-12 bg-surface">
          <router-outlet></router-outlet>
        </main>
      </div>
    </div>
  `
})
export class LayoutComponent implements OnInit {
  private readonly catalog = inject(CatalogStore);
  readonly appVersion = APP_VERSION;

  ngOnInit(): void {
    void this.catalog.ensureLoaded();
  }
}
