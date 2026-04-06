/**
 * Inserts additional directory providers + plans + plan_models (service role required).
 * RLS blocks anon writes; use the service_role key from Supabase Project Settings → API.
 *
 * Usage (from repo root or web/):
 *   SUPABASE_SERVICE_ROLE_KEY="eyJ..." node web/scripts/seed-directory-providers.cjs
 *
 * Optional: SUPABASE_URL (defaults to project URL in environment.ts).
 */

const { createClient } = require('@supabase/supabase-js');

const DEFAULT_URL = 'https://htuflimuceuwjldkupnx.supabase.co';

const seed = [
  {
    provider: {
      name: 'OpenAI Developer Platform',
      slug: 'openai-coding-plan',
      description: 'ChatGPT and API access for coding workflows.',
      website_url: 'https://platform.openai.com'
    },
    plans: [
      { name: 'Individual', slug: 'openai-individual', price_per_month: 20, description: 'Personal use' },
      { name: 'Business', slug: 'openai-business', price_per_month: 40, description: 'Team billing' }
    ]
  },
  {
    provider: {
      name: 'Anthropic Claude Code',
      slug: 'anthropic-claude-code',
      description: 'Claude for coding and agent workflows.',
      website_url: 'https://claude.com'
    },
    plans: [
      { name: 'Pro', slug: 'anthropic-pro', price_per_month: 20, description: 'Standard throughput' },
      { name: 'Max', slug: 'anthropic-max', price_per_month: 100, description: 'Higher limits' }
    ]
  },
  {
    provider: {
      name: 'Google Gemini (Coding)',
      slug: 'google-gemini-coding',
      description: 'Gemini models for IDE and API coding tasks.',
      website_url: 'https://ai.google.dev'
    },
    plans: [
      { name: 'Pro', slug: 'google-gemini-pro', price_per_month: 19.99, description: 'Google AI Pro' },
      { name: 'Ultra', slug: 'google-gemini-ultra', price_per_month: 249, description: 'Ultra tier' }
    ]
  }
];

async function main() {
  const url = process.env.SUPABASE_URL || DEFAULT_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!key || key.length < 20) {
    console.error(
      'Missing SUPABASE_SERVICE_ROLE_KEY. Set it to your Supabase service_role secret (never commit it).\n' +
        'Example: SUPABASE_SERVICE_ROLE_KEY="..." node web/scripts/seed-directory-providers.cjs'
    );
    process.exit(1);
  }

  const supabase = createClient(url, key);

  const { data: modelRow, error: modelErr } = await supabase
    .from('models')
    .select('id')
    .eq('slug', 'kimi-k2.5')
    .maybeSingle();

  if (modelErr) {
    throw modelErr;
  }
  if (!modelRow?.id) {
    throw new Error('Could not find model slug "kimi-k2.5" — add a model row first.');
  }
  const modelId = modelRow.id;

  for (const entry of seed) {
    const { provider } = entry;

    const { data: existing } = await supabase.from('providers').select('id').eq('slug', provider.slug).maybeSingle();

    let providerId;
    if (existing?.id) {
      console.log(`Skip provider (exists): ${provider.slug}`);
      providerId = existing.id;
    } else {
      const { data: ins, error } = await supabase.from('providers').insert(provider).select('id').single();
      if (error) {
        throw error;
      }
      providerId = ins.id;
      console.log(`Inserted provider: ${provider.slug}`);
    }

    for (const plan of entry.plans) {
      const { data: pExisting } = await supabase
        .from('plans')
        .select('id')
        .eq('provider_id', providerId)
        .eq('slug', plan.slug)
        .maybeSingle();

      let planId;
      if (pExisting?.id) {
        console.log(`  Skip plan (exists): ${plan.slug}`);
        planId = pExisting.id;
      } else {
        const { data: pIns, error: pErr } = await supabase
          .from('plans')
          .insert({
            provider_id: providerId,
            name: plan.name,
            slug: plan.slug,
            description: plan.description ?? null,
            price_per_month: plan.price_per_month,
            currency: 'USD',
            is_active: true
          })
          .select('id')
          .single();
        if (pErr) {
          throw pErr;
        }
        planId = pIns.id;
        console.log(`  Inserted plan: ${plan.slug}`);
      }

      const { data: jExisting } = await supabase
        .from('plan_models')
        .select('plan_id')
        .eq('plan_id', planId)
        .eq('model_id', modelId)
        .maybeSingle();

      if (jExisting) {
        console.log(`    Skip plan_models (exists): ${plan.slug} + kimi-k2.5`);
        continue;
      }

      const { error: jErr } = await supabase.from('plan_models').insert({
        plan_id: planId,
        model_id: modelId
      });
      if (jErr) {
        throw jErr;
      }
      console.log(`    Linked plan_models: ${plan.slug} → kimi-k2.5`);
    }
  }

  console.log('Done.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
