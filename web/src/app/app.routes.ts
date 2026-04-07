import { Routes } from '@angular/router';
import { LayoutComponent } from './components/layout/layout.component';
import { DirectoryComponent } from './pages/directory/directory.component';
import { PlanComponent } from './pages/plan/plan.component';
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
        path: 'directory/:providerId/:planId/:modelSlug',
        component: PlanComponent
      },
      {
        path: 'directory/:providerId/:planId',
        component: PlanComponent
      },
      {
        path: 'directory/:providerId',
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
