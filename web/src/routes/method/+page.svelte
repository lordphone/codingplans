<script lang="ts">
	import { lab } from '#lib/data.ts';
	import { fmtEffect } from '#lib/labstats.ts';
	import { site } from '#lib/site.ts';
	import { resolve } from '$app/paths';

	const ref = lab[0];
	const margin = (p: string) => {
		const pr = ref?.probes[p];
		return pr?.margin == null ? null : fmtEffect(pr.margin, pr.effect_name);
	};

	const faq = [
		[
			'Why aren’t Claude, ChatGPT or Copilot subscriptions listed?',
			'Those subscriptions are only usable through their own apps and coding tools, not as a plain API endpoint, so the same requests cannot be sent to the plan and to the paid API side by side. Their models are also closed, so there is no independent copy of the weights to anchor a lab test.'
		],
		[
			'Why not just run a public benchmark on each plan?',
			'A benchmark score says how good a model is, not whether it is the model you paid for. Small precision cuts barely move benchmark scores while still changing outputs; comparing against the provider’s own API on identical requests isolates exactly the difference that matters.'
		],
		[
			'Some plans show only a few applicable probes. Why?',
			'Several 2026 models always reason before answering and ignore sampling settings. The accuracy and distribution probes need direct answers, so on those models only caching, token accounting and speed can run for now. A reasoning-aware variant of the quality probes is planned.'
		],
		[
			'Can a provider game this?',
			'A provider that recognises audit traffic could serve it the genuine model. Requests are paced like a person’s, panels are generated from seeds and can be rotated, and accounts are ordinary paid ones, but a black-box test is never proof against a determined adversary.'
		],
		[
			'Why test on a 7B model when plans serve models 100× larger?',
			'The lab validates the detection methods, not the providers’ models: whether a probe can tell quantized from full-precision weights, a capped context from a full one, faked caching from real caching. The size sweep shows how detection gets harder as models grow, so the numbers are read as lower bounds.'
		],
		[
			'Does a flagged gap mean the provider is cheating?',
			'No. It means the plan behaved measurably differently from the provider’s API on the same requests, by more than honest serving differences explain. Disclosed limits, routing policies or plain bugs can all cause that; providers can reply and their reply is published alongside.'
		]
	];

	const probes = [
		{
			id: 'logprob',
			name: 'Next-token distribution',
			needs: 'logprobs on both endpoints',
			how: 'Each prompt is sent twice per endpoint at temperature 0 with top-5 logprobs. At every position where both completions share the same greedy prefix, we compare the two next-token distributions by total variation. The statistic is the cross-endpoint distance minus the within-endpoint distance, so batch nondeterminism cancels; the p-value comes from re-pairing the four completions of each prompt.'
		},
		{
			id: 'distribution',
			name: 'Answer distribution',
			needs: 'reasoning switched off (no logprobs needed)',
			how: 'Short open questions (“name an animal”, “pick a number”) are sampled 32 times each at temperature 1. We measure the total variation between the two answer distributions per prompt and subtract what label-shuffling produces, which removes the bias finite samples add.'
		},
		{
			id: 'arithmetic',
			name: 'Mental arithmetic',
			needs: 'reasoning switched off',
			how: 'Multiplication of 2–4 digit numbers with no working shown. Quantization damage concentrates in exact multi-step execution, so this moves before general benchmarks do. Paired by item; p from a sign-flip test.'
		},
		{
			id: 'code',
			name: 'Coding tasks',
			needs: 'reasoning switched off',
			how: 'The 164 HumanEval problems, graded by running their hidden unit tests in a network-less container. Paired by task.'
		},
		{
			id: 'needle',
			name: 'Long-context recall',
			needs: 'reasoning switched off',
			how: 'A six-digit code hidden in pseudo-prose of 1K–24K tokens, alongside two decoys of the same shape. A context cap shows as a cliff at some length; KV-cache quantization as a gradual decline.'
		},
		{
			id: 'cache',
			name: 'Prompt caching',
			needs: 'nothing',
			how: 'A fresh 6K-token document (with a per-run nonce so it cannot already be cached) is sent twice in a row. Real prefix caching makes the second time-to-first-token much shorter. Comparing the speed-up with the cached tokens the API reports separates real, missing, and “phantom” caching.'
		},
		{
			id: 'accounting',
			name: 'Token accounting',
			needs: 'usage in the response',
			how: 'Same model, same tokenizer: the same request must cost the same prompt tokens on both endpoints. A constant surplus is a hidden system prompt; a different slope against length is a different tokenizer, which means a different model.'
		},
		{
			id: 'speed',
			name: 'Speed',
			needs: 'nothing',
			how: 'A fixed workload sent one request at a time: time to first token and single-stream decode speed. This is per-request latency, not serving capacity.'
		}
	];
</script>

<svelte:head>
	<title>Method — {site.name}</title>
</svelte:head>

<article class="mx-auto max-w-3xl px-4 pt-14 sm:px-6">
	<p class="eyebrow">Method</p>
	<h1 class="mt-3 text-3xl font-semibold sm:text-4xl">How an audit works</h1>

	<div class="prose-body mt-6 text-ink-2">
		<p>
			A coding plan is audited against <strong class="text-ink">the same provider’s</strong> official
			pay-per-token API for the same model. The question is not whether the model is good but whether
			the plan serves the same thing you would get by paying per token.
		</p>
	</div>

	<ol class="mt-8 space-y-6">
		{#each [['Same requests, same time', 'Both endpoints get the identical panel of requests in one shuffled, interleaved schedule, so time-of-day load and silent version bumps hit both sides equally. Requests are paced, with jitter, at a rate a person could plausibly produce.'], ['One comparison per probe', 'Each probe turns the two sets of responses into an effect size (how different) and a p-value (how sure). Effects are signed so that positive means the plan is further from the API, or worse.'], ['Correct for many tests', 'An audit runs several probes, so p-values are adjusted across the battery with Benjamini–Hochberg before anything is called significant.'], ['Significant is not enough', 'Two honest deployments of the same weights on different hardware are never bit-identical; with enough requests, something always differs. A gap is reported only when the effect also exceeds a margin set in the calibration lab: larger than any legitimate serving difference we could produce.'], ['Publish everything', 'Each audit, its configuration and all lab results go into a public dataset. Raw responses stay local because they include provider output, but the code that produces every number is open.']] as [title, body], i (title)}
			<li class="grid grid-cols-[2rem_1fr] gap-3">
				<span
					class="num mt-0.5 flex size-7 items-center justify-center rounded-full border border-line text-xs text-ink-2"
					>{i + 1}</span
				>
				<div>
					<h2 class="font-medium">{title}</h2>
					<p class="mt-1 text-sm text-ink-2">{body}</p>
				</div>
			</li>
		{/each}
	</ol>

	<h2 class="mt-14 text-2xl font-semibold">The probes</h2>
	<div class="mt-6 divide-y divide-line border-y border-line">
		{#each probes as p (p.id)}
			<section class="py-5">
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<h3 class="font-medium">{p.name}</h3>
					<span class="num text-xs text-muted"
						>{p.id}{margin(p.id) ? ` · margin ${margin(p.id)}` : ''}</span
					>
				</div>
				<p class="mt-1.5 text-sm text-ink-2">{p.how}</p>
				<p class="mt-2 text-xs text-muted">Needs: {p.needs}</p>
			</section>
		{/each}
	</div>

	<h2 class="mt-14 text-2xl font-semibold">Calibration</h2>
	<div class="prose-body mt-3 text-ink-2">
		<p>
			Every probe is first run in the <a class="link" href={resolve('/lab')}>lab</a>: an open model
			served on our own GPU in known configurations. Honest variations (fresh restarts, FP16 instead
			of BF16, eager execution, a different attention kernel) set each probe’s margin. Deliberate
			corner-cuts (INT4 and FP8 weights, quantized KV cache, smaller models under the same name,
			disabled or faked caching, middle-out truncation, an injected system prompt, throttling) show
			what each probe can and cannot see, and at what cost in requests.
		</p>
		<p>
			Gateway-level cuts are simulated by an open-source adversary proxy in front of the inference
			server; engine-level cuts are real vLLM configurations.
		</p>
	</div>

	<h2 class="mt-14 text-2xl font-semibold">Limits and ground rules</h2>
	<ul class="mt-4 list-disc space-y-2.5 pl-5 text-sm text-ink-2">
		<li>
			Results are measured differences, not accusations of fraud. Plans may disclose some limits,
			such as a smaller context window, and a difference can have honest causes.
		</li>
		<li>
			Text-only tests have limited power against careful FP8/INT8 quantization of very large models
			(Cai et al., 2025). The lab publishes exactly how detection power falls as models grow.
		</li>
		<li>
			Test accounts must look like ordinary paying customers. We never use free plans or credits
			from the providers being audited, who would know those accounts and could serve them
			differently.
		</li>
		<li>
			Several plans’ terms restrict automated use. Each plan page states that risk; audits keep
			volume low and identify themselves with an honest User-Agent.
		</li>
		<li>
			A provider who can recognise audit traffic can serve it the genuine model. Panels are
			generated from seeds so they can be rotated, but no black-box test is proof against a
			determined adversary.
		</li>
	</ul>
	<h2 id="faq" class="mt-14 scroll-mt-20 text-2xl font-semibold">Questions</h2>
	<div class="mt-4 divide-y divide-line border-y border-line">
		{#each faq as [q, a] (q)}
			<details class="group py-4">
				<summary
					class="flex cursor-pointer list-none items-center justify-between gap-4 font-medium"
				>
					{q}
					<span class="text-muted transition-transform group-open:rotate-45" aria-hidden="true"
						>+</span
					>
				</summary>
				<p class="mt-2 text-sm text-ink-2">{a}</p>
			</details>
		{/each}
	</div>
</article>
