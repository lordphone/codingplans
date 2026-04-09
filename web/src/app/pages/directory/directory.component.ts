import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CatalogRefreshStripComponent } from '../../components/catalog-refresh-strip/catalog-refresh-strip.component';
import { CatalogStore } from '../../services/catalog-store.service';
import { formatTtftSeconds } from '../../shared/format-metrics';
import type { DirectoryModelRow, DirectoryPlan, DirectoryProvider } from './directory.models';

interface DirectoryViewModel {
  providers: DirectoryProvider[];
  rowCount: number;
  maxTps: number;
}

function modelRowMatchesQuery(
  row: DirectoryModelRow,
  plan: DirectoryPlan,
  provider: DirectoryProvider,
  query: string
): boolean {
  return (
    row.modelName.toLowerCase().includes(query) ||
    row.quantization.toLowerCase().includes(query) ||
    plan.name.toLowerCase().includes(query) ||
    plan.id.toLowerCase().includes(query) ||
    provider.name.toLowerCase().includes(query) ||
    provider.id.toLowerCase().includes(query)
  );
}

function filterProvidersForSearch(providers: DirectoryProvider[], rawQuery: string): DirectoryProvider[] {
  const query = rawQuery.trim().toLowerCase();
  if (!query) {
    return providers;
  }

  return providers
    .map(provider => ({
      ...provider,
      plans: provider.plans
        .map(plan => ({
          ...plan,
          modelRows: plan.modelRows.filter(row => modelRowMatchesQuery(row, plan, provider, query))
        }))
        .filter(plan => plan.modelRows.length > 0)
    }))
    .filter(p => p.plans.length > 0);
}

function buildDirectoryView(providers: DirectoryProvider[], rawQuery: string): DirectoryViewModel {
  const filtered = filterProvidersForSearch(providers, rawQuery);
  const rowCount = filtered.reduce(
    (sum, p) => sum + p.plans.reduce((s, pl) => s + pl.modelRows.length, 0),
    0
  );
  const tpsValues = filtered.flatMap(p => p.plans.flatMap(pl => pl.modelRows.map(r => r.tps)));
  const maxTps = Math.max(1, ...tpsValues);

  return { providers: filtered, rowCount, maxTps };
}

function computeTpsBarPercent(tps: number, maxTps: number): number {
  if (maxTps <= 0) return 0;
  return Math.round((tps / maxTps) * 100);
}

@Component({
  selector: 'app-directory',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule, CatalogRefreshStripComponent],
  templateUrl: './directory.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class DirectoryComponent {
  private readonly catalog = inject(CatalogStore);

  /** Shared `<th>` classes (bordered columns vs last column). */
  readonly tableHeadCellClass =
    'border-r border-zinc-200 bg-zinc-50 px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-wide text-zinc-600';
  readonly tableHeadLastCellClass =
    'bg-zinc-50 px-4 py-3 text-right font-mono text-[10px] font-medium uppercase tracking-wide text-zinc-600';

  readonly tableHeadColumns = [
    { id: 'tier', label: 'Tier' },
    { id: 'model', label: 'Model' },
    { id: 'quantization', label: 'Quantization' },
    { id: 'performance', label: 'Performance' },
    { id: 'cost', label: 'Cost' }
  ] as const;

  readonly searchQuery = signal('');
  readonly loading = this.catalog.loading;
  readonly loadError = this.catalog.loadError;

  readonly view = computed(() => buildDirectoryView(this.catalog.providers(), this.searchQuery()));

  tpsBarPercent(tps: number, maxTps: number): number {
    return computeTpsBarPercent(tps, maxTps);
  }

  formatTtft(seconds: number | null): string {
    return formatTtftSeconds(seconds);
  }

  /** “Loss Detected” only when the benchmark label calls out scam/reset; INT4/INT8 are red without this line. */
  showsQuantizationLossNotice(row: DirectoryModelRow): boolean {
    if (row.quantizationStatus !== 'scam') {
      return false;
    }
    const q = row.quantization.toLowerCase();
    return q.includes('scam') || /\breset\b/.test(q);
  }
}
