import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { from, map, switchMap } from 'rxjs';
import { BackToDirectoryLinkComponent } from '../../components/back-to-directory-link/back-to-directory-link.component';
import { CatalogRefreshStripComponent } from '../../components/catalog-refresh-strip/catalog-refresh-strip.component';
import { CatalogStore } from '../../services/catalog-store.service';
import type { ProviderPageData } from './provider.models';

@Component({
  selector: 'app-provider',
  standalone: true,
  imports: [CommonModule, RouterLink, BackToDirectoryLinkComponent, CatalogRefreshStripComponent],
  templateUrl: './provider.component.html'
})
export class ProviderComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly catalog = inject(CatalogStore);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly providerPage = signal<ProviderPageData | null>(null);

  /** Route param `providerId` is the provider `slug` (directory URLs). */
  providerSlug = '';

  ngOnInit(): void {
    this.route.paramMap
      .pipe(
        switchMap(params => {
          const slug = params.get('providerId') ?? '';
          return from(this.catalog.ensureLoaded()).pipe(map(() => slug));
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(slug => {
        this.providerSlug = slug;
        void this.loadPage(slug);
      });
  }

  private async loadPage(slug: string): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    this.providerPage.set(null);

    if (!slug.trim()) {
      this.loadError.set('Missing provider.');
      this.loading.set(false);
      return;
    }

    const catalogErr = this.catalog.loadError();
    if (catalogErr) {
      this.loadError.set(catalogErr);
      this.loading.set(false);
      return;
    }

    const data = this.catalog.getProviderPage(slug);
    this.providerPage.set(data);
    if (!data) {
      this.loadError.set('Provider not found.');
    }
    this.loading.set(false);
  }
}
