import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';

type QuantizationStatus = 'scam' | 'verified';

/** One line in the grid: a single model under a plan with its own benchmarks. */
interface DirectoryModelRow {
  /** Stable key for @for track (plan slug + model slug or similar). */
  rowId: string;
  modelName: string;
  /** Monthly usage cap / policy copy (maps to product limits later). */
  usageLabel: string;
  tps: number;
  /** Time to first token in seconds; null when not measured. */
  ttftS: number | null;
  quantization: string;
  quantizationStatus: QuantizationStatus;
}

interface DirectoryPlan {
  id: string;
  name: string;
  subtitle: string;
  price: string;
  period: string;
  modelRows: DirectoryModelRow[];
}

interface DirectoryProvider {
  id: string;
  name: string;
  providerId: string;
  plans: DirectoryPlan[];
}

interface DirectoryViewModel {
  providers: DirectoryProvider[];
  /** Total model rows (grid lines) after search */
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

const DIRECTORY_SEED_PROVIDERS: DirectoryProvider[] = [
  {
    id: 'alibaba-model-studio',
    name: 'Alibaba Model Studio',
    providerId: 'BABA-99',
    plans: [
      {
        id: 'lite',
        name: 'Lite',
        subtitle: 'Entry Level Core',
        price: '$10.00',
        period: '/ Month',
        modelRows: [
          {
            rowId: 'lite-qwen-2-5',
            modelName: 'Qwen 2.5',
            usageLabel: '300K tokens / mo · shared pool',
            tps: 45.2,
            ttftS: 0.38,
            quantization: 'INT4 SCAM',
            quantizationStatus: 'scam'
          },
          {
            rowId: 'lite-glm-4',
            modelName: 'GLM-4',
            usageLabel: '300K tokens / mo · shared pool',
            tps: 52.1,
            ttftS: 0.29,
            quantization: 'FP16 FULL',
            quantizationStatus: 'verified'
          }
        ]
      },
      {
        id: 'pro',
        name: 'Pro',
        subtitle: 'Advanced Enterprise',
        price: '$50.00',
        period: '/ Month',
        modelRows: [
          {
            rowId: 'pro-qwen-2-5',
            modelName: 'Qwen 2.5',
            usageLabel: '2M tokens / mo · priority',
            tps: 98.4,
            ttftS: 0.31,
            quantization: 'FP16 FULL',
            quantizationStatus: 'verified'
          },
          {
            rowId: 'pro-kimi-k2-5',
            modelName: 'Kimi K2.5',
            usageLabel: '2M tokens / mo · priority',
            tps: 112.8,
            ttftS: 0.27,
            quantization: 'FP16 FULL',
            quantizationStatus: 'verified'
          }
        ]
      }
    ]
  },
  {
    id: 'z-ai',
    name: 'Z.ai',
    providerId: 'Z-THETA',
    plans: [
      {
        id: 'developer-bundle',
        name: 'Developer Bundle',
        subtitle: 'Indie Compute Pack',
        price: '$20.00',
        period: '/ Month',
        modelRows: [
          {
            rowId: 'dev-minimax',
            modelName: 'MiniMax M2.5',
            usageLabel: '500K tokens / mo',
            tps: 72.0,
            ttftS: 0.41,
            quantization: 'FP16 FULL',
            quantizationStatus: 'verified'
          },
          {
            rowId: 'dev-glm-4',
            modelName: 'GLM-4',
            usageLabel: '500K tokens / mo',
            tps: 78.5,
            ttftS: null,
            quantization: 'FP16 FULL',
            quantizationStatus: 'verified'
          }
        ]
      }
    ]
  }
];

@Component({
  selector: 'app-directory',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './directory.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class DirectoryComponent {
  readonly searchQuery = signal('');

  readonly providers = signal(DIRECTORY_SEED_PROVIDERS);

  readonly view = computed(() => buildDirectoryView(this.providers(), this.searchQuery()));

  barWidthPercent(tps: number, maxTps: number): number {
    return tpsBarPercent(tps, maxTps);
  }

  quantizationLabel(status: QuantizationStatus): string {
    return status === 'scam' ? 'Loss Detected' : 'Verified Zero Loss';
  }

  /** TTFT from `benchmark_runs.ttft_s`; null / NaN shown as em dash. */
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
