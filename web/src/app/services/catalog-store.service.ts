import { Injectable, inject, signal } from '@angular/core';
import type { DirectoryProvider } from '../pages/directory/directory.models';
import type { PlanPerformancePage } from '../pages/plan/plan.models';
import type { ProviderPageData } from '../pages/provider/provider.models';
import type { DirectoryFetchResult } from './supabase.service';
import { SupabaseService } from './supabase.service';

/** Align with benchmark write cadence (~3h); avoids refetching the full catalog on every navigation. */
const CACHE_TTL_MS = 3 * 60 * 60 * 1000;

const SESSION_KEY = 'codingplans.catalog.v1';

interface PersistedCatalogPayload {
  fetchedAt: number;
  providers: DirectoryProvider[];
  planEntries: [string, PlanPerformancePage][];
  providerEntries: [string, ProviderPageData][];
}

/**
 * Single in-memory (and optional session) cache for directory, plan, and provider views.
 * Populated from one `fetchDirectoryFromSupabase` call; not owned by any route component.
 */
@Injectable({
  providedIn: 'root'
})
export class CatalogStore {
  private readonly supabase = inject(SupabaseService);

  private readonly _providers = signal<DirectoryProvider[]>([]);
  private readonly _planPagesByKey = signal(new Map<string, PlanPerformancePage>());
  private readonly _providerPagesBySlug = signal(new Map<string, ProviderPageData>());
  private readonly _loading = signal(false);
  private readonly _error = signal<string | null>(null);
  private readonly _fetchedAt = signal<number | null>(null);

  private inflight: Promise<void> | null = null;

  readonly providers = this._providers.asReadonly();
  readonly loading = this._loading.asReadonly();
  readonly loadError = this._error.asReadonly();
  readonly fetchedAt = this._fetchedAt.asReadonly();

  /** `providerSlug::planSlug` — matches keys built in `SupabaseService`. */
  getPlanPage(providerSlug: string, planSlug: string): PlanPerformancePage | null {
    return this._planPagesByKey().get(`${providerSlug}::${planSlug}`) ?? null;
  }

  getProviderPage(providerSlug: string): ProviderPageData | null {
    return this._providerPagesBySlug().get(providerSlug) ?? null;
  }

  /**
   * Ensures catalog data is available: uses memory, then sessionStorage, then Supabase.
   * Safe to call from every page; concurrent calls share one network request.
   */
  async ensureLoaded(options?: { force?: boolean }): Promise<void> {
    const force = options?.force ?? false;

    if (!force) {
      if (this._fetchedAt() !== null && this.isFresh(this._fetchedAt()!)) {
        return;
      }
      if (this.tryHydrateFromSession()) {
        return;
      }
      if (this.inflight) {
        return this.inflight;
      }
    } else {
      if (this.inflight) {
        await this.inflight;
      }
    }

    this.inflight = this.performNetworkFetch().finally(() => {
      this.inflight = null;
    });
    return this.inflight;
  }

  /** Drop cache and fetch again (e.g. future “Refresh” control). */
  async refresh(): Promise<void> {
    await this.ensureLoaded({ force: true });
  }

  private isFresh(fetchedAt: number): boolean {
    return Date.now() - fetchedAt < CACHE_TTL_MS;
  }

  private tryHydrateFromSession(): boolean {
    if (typeof sessionStorage === 'undefined') {
      return false;
    }
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) {
        return false;
      }
      const p = JSON.parse(raw) as PersistedCatalogPayload;
      if (!p.fetchedAt || !this.isFresh(p.fetchedAt)) {
        sessionStorage.removeItem(SESSION_KEY);
        return false;
      }
      this.applyResult(
        {
          providers: p.providers,
          planPagesByKey: new Map(p.planEntries),
          providerPagesBySlug: new Map(p.providerEntries)
        },
        p.fetchedAt
      );
      return true;
    } catch {
      sessionStorage.removeItem(SESSION_KEY);
      return false;
    }
  }

  private persistSession(fetchedAt: number, result: DirectoryFetchResult): void {
    if (typeof sessionStorage === 'undefined') {
      return;
    }
    try {
      const payload: PersistedCatalogPayload = {
        fetchedAt,
        providers: result.providers,
        planEntries: [...result.planPagesByKey.entries()],
        providerEntries: [...result.providerPagesBySlug.entries()]
      };
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload));
    } catch {
      /* quota or private mode */
    }
  }

  private applyResult(result: DirectoryFetchResult, fetchedAt: number): void {
    this._providers.set(result.providers);
    this._planPagesByKey.set(result.planPagesByKey);
    this._providerPagesBySlug.set(result.providerPagesBySlug);
    this._fetchedAt.set(fetchedAt);
    this._error.set(null);
  }

  private clearState(message: string | null): void {
    this._providers.set([]);
    this._planPagesByKey.set(new Map());
    this._providerPagesBySlug.set(new Map());
    this._fetchedAt.set(null);
    this._error.set(message);
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.removeItem(SESSION_KEY);
    }
  }

  private async performNetworkFetch(): Promise<void> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const result = await this.supabase.fetchDirectoryFromSupabase();
      const now = Date.now();
      this.applyResult(result, now);
      this.persistSession(now, result);
    } catch (e: unknown) {
      console.error('Catalog load failed', e);
      const message =
        e && typeof e === 'object' && 'message' in e && typeof (e as { message: unknown }).message === 'string'
          ? (e as { message: string }).message
          : 'Could not load catalog from Supabase.';
      this.clearState(message);
    } finally {
      this._loading.set(false);
    }
  }
}
