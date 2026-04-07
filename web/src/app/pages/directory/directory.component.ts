import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DirectorySnapshotService } from '../../services/directory-snapshot.service';
import { SupabaseService } from '../../services/supabase.service';
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
    row.usageLabel.toLowerCase().includes(query) ||
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
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './directory.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class DirectoryComponent implements OnInit {
  private readonly supabase = inject(SupabaseService);
  private readonly directorySnapshot = inject(DirectorySnapshotService);

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
    { id: 'usage', label: 'Usage limits' },
    { id: 'cost', label: 'Cost' }
  ] as const;

  readonly searchQuery = signal('');
  readonly providers = signal<DirectoryProvider[]>([]);
  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);

  readonly view = computed(() => buildDirectoryView(this.providers(), this.searchQuery()));

  async ngOnInit(): Promise<void> {
    this.loadError.set(null);
    this.loading.set(true);
    try {
      const data = await this.supabase.fetchDirectoryFromSupabase();
      this.providers.set(data);
      this.directorySnapshot.setProviders(data);
    } catch (e) {
      console.error('Directory load failed', e);
      const message =
        e && typeof e === 'object' && 'message' in e && typeof (e as { message: unknown }).message === 'string'
          ? (e as { message: string }).message
          : 'Could not load directory from Supabase.';
      this.loadError.set(message);
      this.providers.set([]);
      this.directorySnapshot.setProviders([]);
    } finally {
      this.loading.set(false);
    }
  }

  tpsBarPercent(tps: number, maxTps: number): number {
    return computeTpsBarPercent(tps, maxTps);
  }

  formatTtft(seconds: number | null): string {
    if (seconds == null || Number.isNaN(seconds)) {
      return '—';
    }
    if (seconds < 1) {
      return `${Math.round(seconds * 1000)} ms`;
    }
    return `${seconds.toFixed(2)} s`;
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
