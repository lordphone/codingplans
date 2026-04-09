import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { DirectoryComponent } from './directory.component';
import type { DirectoryModelRow, DirectoryPlan, DirectoryProvider } from './directory.models';
import { CatalogStore } from '../../services/catalog-store.service';

/** Resolves change detection (zone + microtasks). */
async function flushView(fixture: { detectChanges: () => void; whenStable: () => Promise<unknown> }) {
  fixture.detectChanges();
  await fixture.whenStable();
  await Promise.resolve();
  fixture.detectChanges();
  await fixture.whenStable();
}

function row(overrides: Partial<DirectoryModelRow> = {}): DirectoryModelRow {
  return {
    rowId: 'plan-a:model-x',
    modelId: '00000000-0000-4000-8000-000000000001',
    modelSlug: 'model-x',
    modelName: 'Model X',
    usageLabel: '—',
    tps: 50,
    ttftS: 0.2,
    quantization: 'fp16',
    quantizationStatus: 'verified',
    ...overrides
  };
}

function plan(overrides: Partial<DirectoryPlan> = {}): DirectoryPlan {
  return {
    id: 'starter',
    name: 'Starter Plan',
    subtitle: '',
    price: '$10',
    period: '/ month',
    modelRows: [row()],
    ...overrides
  };
}

function provider(overrides: Partial<DirectoryProvider> = {}): DirectoryProvider {
  return {
    id: 'acme-ai',
    name: 'Acme AI',
    plans: [plan()],
    ...overrides
  };
}

describe('DirectoryComponent', () => {
  function mockProviders(): DirectoryProvider[] {
    return [
      {
        id: 'test-provider',
        name: 'Test Provider',
        plans: [
          {
            id: 'basic',
            name: 'Basic',
            subtitle: 'For testing',
            price: '$20',
            period: '/ month',
            modelRows: [
              {
                rowId: 'basic:gpt',
                modelId: '00000000-0000-4000-8000-000000000002',
                modelSlug: 'gpt',
                modelName: 'GPT-Test',
                usageLabel: '—',
                tps: 120,
                ttftS: 0.35,
                quantization: 'fp16',
                quantizationStatus: 'verified'
              }
            ]
          }
        ]
      }
    ];
  }

  async function setup(state?: { providers?: DirectoryProvider[]; loading?: boolean; error?: string | null }) {
    const providersSig = signal(state?.providers ?? []);
    const loadingSig = signal(state?.loading ?? false);
    const errorSig = signal(state?.error ?? null);
    const mockStore = {
      providers: providersSig.asReadonly(),
      loading: loadingSig.asReadonly(),
      loadError: errorSig.asReadonly(),
      fetchedAt: signal<number | null>(null).asReadonly(),
      ensureLoaded: vi.fn().mockResolvedValue(undefined),
      getPlanPage: vi.fn(),
      getProviderPage: vi.fn(),
      refresh: vi.fn()
    };
    await TestBed.configureTestingModule({
      imports: [DirectoryComponent],
      providers: [{ provide: CatalogStore, useValue: mockStore }, provideRouter([])]
    }).compileComponents();

    const fixture = TestBed.createComponent(DirectoryComponent);
    const component = fixture.componentInstance;
    await flushView(fixture);
    return { fixture, component, providersSig, loadingSig, errorSig };
  }

  it('should create', async () => {
    const { component } = await setup();
    expect(component).toBeTruthy();
  });

  it('reflects catalog providers in the view model', async () => {
    const data = mockProviders();
    const { component } = await setup({ providers: data, loading: false });

    expect(component.loading()).toBe(false);
    expect(component.loadError()).toBeNull();
    expect(component.view().rowCount).toBe(1);
  });

  it('shows catalog load error from store', async () => {
    const { component } = await setup({ providers: [], error: 'network', loading: false });

    expect(component.loadError()).toBe('network');
  });

  it('shows empty dataset copy when catalog has no providers', async () => {
    const { fixture } = await setup({ providers: [] });
    const el = fixture.nativeElement as HTMLElement;

    expect(el.textContent).toContain('No providers in the directory yet.');
  });

  it('shows no search results when query matches nothing', async () => {
    const { fixture, component } = await setup({ providers: mockProviders() });
    component.searchQuery.set('zzzz-not-found');
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No directory entries match your search.');
  });

  it('updates result count when search filters rows', async () => {
    const { fixture, component } = await setup({ providers: mockProviders() });

    expect(fixture.nativeElement.textContent).toContain('1 RESULTS');

    component.searchQuery.set('GPT-Test');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('1 RESULTS');

    component.searchQuery.set('nothing');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('0 RESULTS');
  });

  it('renders provider name and table headers', async () => {
    const { fixture } = await setup({ providers: mockProviders() });
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('h1')?.textContent?.trim()).toBe('Provider & Plan Directory');
    expect(el.textContent).toContain('Test Provider');
    expect(el.textContent).toContain('Tier');
    expect(el.textContent).toContain('Quantization');
  });

  describe('search and view()', () => {
    it('leaves data unchanged when query is empty or whitespace', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      const p1 = provider({
        id: 'p1',
        name: 'Alpha',
        plans: [
          plan({ id: 'lite', name: 'Lite', modelRows: [row({ rowId: '1', modelName: 'Fast' })] }),
          plan({ id: 'pro', name: 'Pro', modelRows: [row({ rowId: '2', modelName: 'Slow' })] })
        ]
      });
      providersSig.set([p1]);

      component.searchQuery.set('');
      expect(component.view().providers).toEqual([p1]);

      component.searchQuery.set('   ');
      expect(component.view().providers).toEqual([p1]);
    });

    it('keeps only plans with matching rows', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      const p1 = provider({
        id: 'p1',
        name: 'Alpha',
        plans: [
          plan({ id: 'lite', name: 'Lite', modelRows: [row({ rowId: '1', modelName: 'Fast' })] }),
          plan({ id: 'pro', name: 'Pro', modelRows: [row({ rowId: '2', modelName: 'Slow' })] })
        ]
      });
      providersSig.set([p1]);
      component.searchQuery.set('fast');

      const vm = component.view();
      expect(vm.providers).toHaveLength(1);
      expect(vm.providers[0].plans).toHaveLength(1);
      expect(vm.providers[0].plans[0].id).toBe('lite');
      expect(vm.providers[0].plans[0].modelRows).toHaveLength(1);
    });

    it('drops providers with no matching plans', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      const p1 = provider({
        id: 'p1',
        name: 'Alpha',
        plans: [
          plan({ id: 'lite', name: 'Lite', modelRows: [row({ rowId: '1', modelName: 'Fast' })] }),
          plan({ id: 'pro', name: 'Pro', modelRows: [row({ rowId: '2', modelName: 'Slow' })] })
        ]
      });
      providersSig.set([p1]);
      component.searchQuery.set('nope');

      expect(component.view().providers).toHaveLength(0);
    });

    it('matches by provider id so rows are not over-filtered', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      const p1 = provider({
        id: 'p1',
        name: 'Alpha',
        plans: [
          plan({ id: 'lite', name: 'Lite', modelRows: [row({ rowId: '1', modelName: 'Fast' })] }),
          plan({ id: 'pro', name: 'Pro', modelRows: [row({ rowId: '2', modelName: 'Slow' })] })
        ]
      });
      providersSig.set([p1]);
      component.searchQuery.set('p1');

      expect(component.view().providers[0].plans.length).toBe(2);
    });

    it('computes rowCount across providers and plans', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      providersSig.set([
        provider({
          plans: [
            plan({ modelRows: [row({ rowId: 'a' }), row({ rowId: 'b' })] }),
            plan({ id: 'x', name: 'X', modelRows: [row({ rowId: 'c' })] })
          ]
        })
      ]);
      component.searchQuery.set('');

      const vm = component.view();
      expect(vm.rowCount).toBe(3);
      expect(vm.providers).toHaveLength(1);
    });

    it('applies search to rowCount', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      providersSig.set([
        provider({
          plans: [
            plan({
              modelRows: [row({ rowId: '1', modelName: 'Keep' }), row({ rowId: '2', modelName: 'Drop' })]
            })
          ]
        })
      ]);
      component.searchQuery.set('keep');

      expect(component.view().rowCount).toBe(1);
    });

    it('sets maxTps to at least 1 when there are no rows', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      providersSig.set([]);
      component.searchQuery.set('');

      const vm = component.view();
      expect(vm.rowCount).toBe(0);
      expect(vm.maxTps).toBe(1);
    });

    it('sets maxTps from the highest tps in the filtered view', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      providersSig.set([
        provider({
          plans: [
            plan({
              modelRows: [
                row({ rowId: 'a', tps: 10 }),
                row({ rowId: 'b', tps: 40 }),
                row({ rowId: 'c', tps: 25 })
              ]
            })
          ]
        })
      ]);
      component.searchQuery.set('');

      expect(component.view().maxTps).toBe(40);
    });

    it('matches search across model, plan, provider, and quantization', async () => {
      const { component, providersSig } = await setup({ providers: [] });
      const p = provider();
      providersSig.set([p]);

      component.searchQuery.set('model x');
      expect(component.view().rowCount).toBe(1);

      component.searchQuery.set('starter');
      expect(component.view().rowCount).toBe(1);

      component.searchQuery.set('acme-ai');
      expect(component.view().rowCount).toBe(1);

      component.searchQuery.set('fp16');
      expect(component.view().rowCount).toBe(1);

      component.searchQuery.set('zzz');
      expect(component.view().rowCount).toBe(0);
    });
  });

  describe('formatTtft', () => {
    it('formats sub-second as milliseconds', async () => {
      const { component } = await setup();
      expect(component.formatTtft(0.042)).toBe('42 ms');
    });

    it('formats seconds with two decimals', async () => {
      const { component } = await setup();
      expect(component.formatTtft(1.5)).toBe('1.50 s');
    });

    it('returns em dash for null or NaN', async () => {
      const { component } = await setup();
      expect(component.formatTtft(null)).toBe('—');
      expect(component.formatTtft(Number.NaN)).toBe('—');
    });
  });

  describe('tpsBarPercent', () => {
    it('returns 0 when maxTps is not positive', async () => {
      const { component } = await setup();
      expect(component.tpsBarPercent(10, 0)).toBe(0);
      expect(component.tpsBarPercent(10, -1)).toBe(0);
    });

    it('returns rounded percentage', async () => {
      const { component } = await setup();
      expect(component.tpsBarPercent(25, 100)).toBe(25);
      expect(component.tpsBarPercent(33, 100)).toBe(33);
    });

    it('is 100 when tps equals max', async () => {
      const { component } = await setup();
      expect(component.tpsBarPercent(100, 100)).toBe(100);
    });
  });
});
