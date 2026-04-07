import { Injectable, signal } from '@angular/core';
import type { DirectoryPlan, DirectoryProvider } from '../pages/directory/directory.models';

/**
 * Last successful directory listing (in-memory). Lets the plan page paint a shell immediately after
 * in-app navigation; chart data still loads from `fetchPlanPerformancePage`.
 */
@Injectable({
  providedIn: 'root'
})
export class DirectorySnapshotService {
  readonly providers = signal<DirectoryProvider[] | null>(null);

  setProviders(data: DirectoryProvider[]): void {
    this.providers.set(data);
  }

  findPlan(providerSlug: string, planSlug: string): { provider: DirectoryProvider; plan: DirectoryPlan } | null {
    const list = this.providers();
    if (!list || list.length === 0) {
      return null;
    }
    const provider = list.find(p => p.id === providerSlug);
    if (!provider) {
      return null;
    }
    const plan = provider.plans.find(pl => pl.id === planSlug);
    if (!plan) {
      return null;
    }
    return { provider, plan };
  }
}
