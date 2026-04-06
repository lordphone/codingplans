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
import { SupabaseService } from '../../services/supabase.service';
import type { DirectoryModelRow, DirectoryPlan, DirectoryProvider, QuantizationStatus } from './directory.models';

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
    provider.name.toLowerCase().includes(query)
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
    .filter(p => p.plans.length > 0 || p.name.toLowerCase().includes(query));
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

function tpsBarPercent(tps: number, maxTps: number): number {
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
    } catch (e) {
      console.error('Directory load failed', e);
      const message =
        e && typeof e === 'object' && 'message' in e && typeof (e as { message: unknown }).message === 'string'
          ? (e as { message: string }).message
          : 'Could not load directory from Supabase.';
      this.loadError.set(message);
      this.providers.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  barWidthPercent(tps: number, maxTps: number): number {
    return tpsBarPercent(tps, maxTps);
  }

  quantizationLabel(status: QuantizationStatus): string {
    return status === 'scam' ? 'Loss Detected' : 'Verified Zero Loss';
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
}
