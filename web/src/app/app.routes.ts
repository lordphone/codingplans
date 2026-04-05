import { Routes } from '@angular/router';
import { LayoutComponent } from './components/layout/layout.component';
import { DirectoryComponent } from './pages/directory/directory.component';
import { ProviderDetailComponent } from './pages/provider-detail/provider-detail.component';

export const routes: Routes = [
  {
    path: '',
    component: LayoutComponent,
    children: [
      {
        path: '',
        redirectTo: 'directory',
        pathMatch: 'full'
      },
      {
        path: 'directory',
        component: DirectoryComponent
      },
      {
        path: 'directory/:providerId',
        component: ProviderDetailComponent
      },
      {
        path: 'directory/:providerId/:planId',
        component: ProviderDetailComponent
      },
      {
        path: 'benchmarks',
        loadComponent: () => import('./pages/benchmarks/benchmarks.component').then(m => m.BenchmarksComponent)
      },
      {
        path: 'models',
        loadComponent: () => import('./pages/models/models.component').then(m => m.ModelsComponent)
      }
    ]
  }
];
