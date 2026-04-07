import { Routes } from '@angular/router';
import { LayoutComponent } from './components/layout/layout.component';
import { DirectoryComponent } from './pages/directory/directory.component';
import { ProviderComponent } from './pages/provider/provider.component';

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
        component: ProviderComponent
      },
      {
        path: 'directory/:providerId/:planId',
        component: ProviderComponent
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
