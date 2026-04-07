import { RenderMode, ServerRoute } from '@angular/ssr';

export const serverRoutes: ServerRoute[] = [
  {
    path: '',
    renderMode: RenderMode.Prerender
  },
  {
    path: 'directory',
    renderMode: RenderMode.Prerender
  },
  {
    path: 'directory/:providerId/:planId/:modelSlug',
    renderMode: RenderMode.Server
  },
  {
    path: 'directory/:providerId/:planId',
    renderMode: RenderMode.Server
  },
  {
    path: 'directory/:providerId',
    renderMode: RenderMode.Server
  },
  {
    path: 'benchmarks',
    renderMode: RenderMode.Server
  },
  {
    path: 'models',
    renderMode: RenderMode.Server
  }
];
