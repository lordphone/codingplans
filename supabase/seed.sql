-- Directory catalog: providers, plans, models and which plan serves which model.
--
-- Idempotent upserts keyed on slugs, so re-running it updates prices/limits in
-- place. Slugs here must match the `audits` section of benchmarks/endpoints.json
-- (benchmarks/selftest.py checks that).
--
-- Prices and limits are a research snapshot from 2026-10-20 (see
-- docs/research/landscape.md); vendors reshuffle them often, so re-check the
-- linked pages before publishing. Run with:
--   psql "$SUPABASE_DB_URL" -f supabase/seed.sql
-- or paste into the Supabase SQL editor. (`supabase db reset` runs it locally.)

insert into public.providers (name, slug, description, website_url) values
  ('Z.ai (Zhipu)', 'zai', 'Maker of the GLM models; sells the GLM Coding Plan.', 'https://z.ai/subscribe'),
  ('Moonshot AI', 'moonshot', 'Maker of the Kimi models; sells Kimi Code through Kimi membership.', 'https://www.kimi.com/code'),
  ('MiniMax', 'minimax', 'Maker of the MiniMax-M models; sells the M Plan.', 'https://platform.minimax.io'),
  ('Alibaba Cloud Model Studio', 'alibaba-cloud-model-studio', 'Resells Qwen, GLM, Kimi and MiniMax models in its Coding Plan.', 'https://www.alibabacloud.com/help/en/model-studio/coding-plan')
on conflict (slug) do update set
  name = excluded.name, description = excluded.description, website_url = excluded.website_url;

insert into public.models (name, slug, description) values
  ('GLM-5', 'glm-5', 'Z.ai GLM-5 (open weights).'),
  ('GLM-5.3', 'glm-5.3', 'Z.ai GLM-5.3 (open weights, BF16/FP8 checkpoints).'),
  ('Kimi K2.5', 'kimi-k2.5', 'Moonshot Kimi K2.5 (open weights).'),
  ('Kimi K3', 'kimi-k3', 'Moonshot Kimi K3 (open weights; thinking always on).'),
  ('MiniMax-M2.5', 'minimax-m2.5', 'MiniMax M2.5 (open weights; retiring 2026-11-18).'),
  ('MiniMax-M3.1-Flash', 'minimax-m3.1-flash', 'MiniMax M3.1 Flash (thinking always on).'),
  ('Qwen3.6-Plus', 'qwen3.6-plus', 'Alibaba Qwen3.6-Plus (closed weights).')
on conflict (slug) do update set name = excluded.name, description = excluded.description;

with p as (select id, slug from public.providers)
insert into public.plans (provider_id, name, slug, description, price_per_month, currency, is_active, url, advertised_limits)
select p.id, v.name, v.slug, v.description, v.price, v.currency, true, v.url, v.limits
from (values
  ('zai', 'GLM Coding Lite', 'zai-glm-coding-lite', 'Entry tier of the GLM Coding Plan.', 18, 'USD',
   'https://z.ai/subscribe', '2,000 credits / 5h · 10,000 / week; off-peak usage billed at 50%'),
  ('zai', 'GLM Coding Pro', 'zai-glm-coding-pro', 'Mid tier of the GLM Coding Plan.', 80, 'USD',
   'https://z.ai/subscribe', '12,000 credits / 5h · 60,000 / week'),
  ('zai', 'GLM Coding Max', 'zai-glm-coding-max', 'Top tier of the GLM Coding Plan.', 168, 'USD',
   'https://z.ai/subscribe', '28,000 credits / 5h · 140,000 / week'),
  ('moonshot', 'Kimi Code Pro', 'kimi-code-pro', 'Kimi membership tier with Kimi Code access.', 199, 'CNY',
   'https://www.kimi.com/code', '5-hour rolling window + monthly quota (no numbers published)'),
  ('minimax', 'M Plan Explore', 'minimax-m-plan-explore', 'Mid tier of the MiniMax M Plan.', 55, 'USD',
   'https://platform.minimax.io', '3× Go tier; 5-hour and weekly windows (no numbers published)'),
  ('alibaba-cloud-model-studio', 'Coding Plan Pro', 'alibaba-coding-pro', 'International Coding Plan; Lite tier closed to new subscribers.', 50, 'USD',
   'https://www.alibabacloud.com/help/en/model-studio/coding-plan', '6,000 requests / 5h · 45,000 / week · 90,000 / month')
) as v(provider_slug, name, slug, description, price, currency, url, limits)
join p on p.slug = v.provider_slug
on conflict (provider_id, slug) do update set
  name = excluded.name, description = excluded.description, price_per_month = excluded.price_per_month,
  currency = excluded.currency, is_active = excluded.is_active, url = excluded.url,
  advertised_limits = excluded.advertised_limits;

insert into public.plan_models (plan_id, model_id)
select pl.id, m.id
from (values
  ('zai', 'zai-glm-coding-lite', 'glm-5.3'),
  ('zai', 'zai-glm-coding-pro', 'glm-5.3'),
  ('zai', 'zai-glm-coding-max', 'glm-5.3'),
  ('moonshot', 'kimi-code-pro', 'kimi-k3'),
  ('minimax', 'minimax-m-plan-explore', 'minimax-m3.1-flash'),
  ('alibaba-cloud-model-studio', 'alibaba-coding-pro', 'glm-5'),
  ('alibaba-cloud-model-studio', 'alibaba-coding-pro', 'kimi-k2.5'),
  ('alibaba-cloud-model-studio', 'alibaba-coding-pro', 'minimax-m2.5'),
  ('alibaba-cloud-model-studio', 'alibaba-coding-pro', 'qwen3.6-plus')
) as v(provider_slug, plan_slug, model_slug)
join public.providers pr on pr.slug = v.provider_slug
join public.plans pl on pl.provider_id = pr.id and pl.slug = v.plan_slug
join public.models m on m.slug = v.model_slug
on conflict (plan_id, model_id) do nothing;
