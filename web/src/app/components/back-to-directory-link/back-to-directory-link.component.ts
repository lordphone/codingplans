import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-back-to-directory-link',
  standalone: true,
  imports: [RouterLink],
  template: `
    <a
      routerLink="/directory"
      class="inline-block font-mono text-[11px] uppercase tracking-wider text-zinc-500 transition-colors hover:text-emerald-700"
    >
      ← Back to directory
    </a>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class BackToDirectoryLinkComponent {}
