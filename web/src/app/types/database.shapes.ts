/**
 * Hand-written types built on top of the DB row shapes in `database.types.ts`.
 * Includes nested PostgREST embed result shapes returned by `.select(...)` queries.
 * Keep this file separate so `npm run db:types` can regenerate `database.types.ts`
 * without clobbering these.
 */

import type { Model, Plan, PlanModel, Provider } from './database.types';

export interface PlanModelWithModel extends PlanModel {
  models: Model;
}

export interface PlanWithModels extends Plan {
  plan_models: PlanModelWithModel[];
}

export interface ProviderWithPlansAndModels extends Provider {
  plans: PlanWithModels[];
}
