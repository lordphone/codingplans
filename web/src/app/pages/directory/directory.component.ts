import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';

// --- Types (UI-facing; map from Supabase in a service when you wire data) ---

type QuantizationStatus = 'scam' | 'verified';

interface DirectoryPlan {
  id: string;
  name: string;
  subtitle: string;
  models: string;
  tps: number;
  quantization: string;
  quantizationStatus: QuantizationStatus;
  price: string;
  period: string;
}

interface DirectoryProvider {
  /** URL slug — e.g. /directory/:providerId */
  id: string;
  name: string;
  /** Display / external reference id */
  providerId: string;
  plans: DirectoryPlan[];
}

interface DirectoryViewModel {
  providers: DirectoryProvider[];
  planCount: number;
  /** Max TPS among visible plans; normalizes bar widths (always >= 1) */
  maxTps: number;
}

// --- Pure helpers (same behavior whether data is seed or API-backed) ---

function planMatchesQuery(plan: DirectoryPlan, provider: DirectoryProvider, query: string): boolean {
  return (
    plan.name.toLowerCase().includes(query) ||
    plan.models.toLowerCase().includes(query) ||
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
      plans: provider.plans.filter(plan => planMatchesQuery(plan, provider, query))
    }))
    .filter(p => p.plans.length > 0 || p.name.toLowerCase().includes(query));
}

function buildDirectoryView(providers: DirectoryProvider[], rawQuery: string): DirectoryViewModel {
  const filtered = filterProvidersForSearch(providers, rawQuery);
  const planCount = filtered.reduce((sum, p) => sum + p.plans.length, 0);
  const tpsValues = filtered.flatMap(p => p.plans.map(pl => pl.tps));
  const maxTps = Math.max(1, ...tpsValues);

  return { providers: filtered, planCount, maxTps };
}

function tpsBarPercent(tps: number, maxTps: number): number {
  if (maxTps <= 0) return 0;
  return Math.round((tps / maxTps) * 100);
}

// --- Placeholder data (replace with providers.set(...) after fetch) ---

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
        models: 'Qwen 2.5 / GLM-4',
        tps: 45.2,
        quantization: 'INT4 SCAM',
        quantizationStatus: 'scam',
        price: '$10.00',
        period: '/ Month'
      },
      {
        id: 'pro',
        name: 'Pro',
        subtitle: 'Advanced Enterprise',
        models: 'Qwen 2.5 / Kimi K2.5',
        tps: 112.8,
        quantization: 'FP16 FULL',
        quantizationStatus: 'verified',
        price: '$50.00',
        period: '/ Month'
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
        models: 'MiniMax M2.5 / GLM-4',
        tps: 78.5,
        quantization: 'FP16 FULL',
        quantizationStatus: 'verified',
        price: '$20.00',
        period: '/ Month'
      }
    ]
  }
];

// --- Component ---

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
}
