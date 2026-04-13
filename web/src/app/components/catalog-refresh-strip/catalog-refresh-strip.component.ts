import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CatalogStore } from '../../services/catalog-store.service';

@Component({
  selector: 'app-catalog-refresh-strip',
  standalone: true,
  template: `
    <div class="flex flex-wrap items-center justify-end gap-2">
      <span class="whitespace-nowrap font-mono text-[10px] tracking-wide text-zinc-500">
        <span class="text-zinc-500">data timestamp:</span>
        <span class="ml-1.5 tabular-nums text-zinc-700">{{ dataTimeValue() }}</span>
      </span>
      <button
        type="button"
        class="rounded-none border border-zinc-300 bg-white px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-wide text-zinc-700 shadow-sm transition-colors hover:border-emerald-600 hover:text-emerald-800 disabled:opacity-50"
        [disabled]="catalog.loading()"
        (click)="onRefresh()"
      >
        Refresh
      </button>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class CatalogRefreshStripComponent {
  readonly catalog = inject(CatalogStore);

  /** Date/time with seconds; shown after the “data timestamp:” label. */
  readonly dataTimeValue = computed(() => {
    const t = this.catalog.fetchedAt();
    if (t != null) {
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'short',
        timeStyle: 'medium'
      }).format(new Date(t));
    }
    if (this.catalog.loading()) {
      return 'Loading…';
    }
    return '—';
  });

  onRefresh(): void {
    void this.catalog.refresh();
  }
}
