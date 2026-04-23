import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-back-to-directory-link',
  standalone: true,
  imports: [RouterLink],
  template: `
    <a
      routerLink="/directory"
      class="inline-block font-mono text-[11px] uppercase tracking-wider text-zinc-500 underline decoration-1 decoration-zinc-200 underline-offset-2 transition-colors hover:text-accent-interactive hover:decoration-accent-interactive/35"
    >
      ← Back to directory
    </a>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class BackToDirectoryLinkComponent {}
