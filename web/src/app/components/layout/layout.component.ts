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
      <nav
        class="fixed top-0 left-0 right-0 z-50 flex min-h-16 w-full min-w-0 items-center justify-between gap-6 border-b border-zinc-200 bg-white px-6 sm:px-12"
      >
        <div class="min-w-0 flex-1">
          <a
            routerLink="/"
            class="block truncate text-lg font-light uppercase tracking-[0.35em] text-primary sm:text-xl sm:tracking-[0.5em]"
          >
            CODING PLAN COMPARISON
          </a>
        </div>
        <div class="flex shrink-0 items-center gap-8 sm:gap-12">
          <a
            routerLink="/directory"
            routerLinkActive="border-b border-primary text-primary"
            [routerLinkActiveOptions]="{ exact: true }"
            class="font-['Inter'] pb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:text-primary"
          >
            DIRECTORY
          </a>
          <a
            routerLink="/benchmarks"
            routerLinkActive="border-b border-primary text-primary"
            class="font-['Inter'] pb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:text-primary"
          >
            BENCHMARKS
          </a>
          <span
            class="whitespace-nowrap border-l border-zinc-200 pl-6 font-mono text-[9px] uppercase text-zinc-400 sm:pl-8"
            aria-label="App version"
          >v{{ appVersion }}</span>
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
