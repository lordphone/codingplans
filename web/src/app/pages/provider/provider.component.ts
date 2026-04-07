import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { SupabaseService } from '../../services/supabase.service';
import type { ProviderPageData } from './provider.models';

@Component({
  selector: 'app-provider',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './provider.component.html'
})
export class ProviderComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly supabase = inject(SupabaseService);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly providerPage = signal<ProviderPageData | null>(null);

  /** Route param `providerId` is the provider `slug` (directory URLs). */
  providerSlug = '';

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      const slug = params.get('providerId') ?? '';
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

    try {
      const data = await this.supabase.fetchProviderPageFromSupabase(slug);
      this.providerPage.set(data);
      if (!data) {
        this.loadError.set('Provider not found.');
      }
    } catch (e: unknown) {
      const message =
        e && typeof e === 'object' && 'message' in e && typeof (e as { message: unknown }).message === 'string'
          ? (e as { message: string }).message
          : 'Could not load provider.';
      this.loadError.set(message);
    } finally {
      this.loading.set(false);
    }
  }
}
