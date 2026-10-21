/**
 * Methodology catalogue: one entry per audit test. `id` matches
 * `audit_results.test_name` and is the anchor on /methodology/ (#<id>).
 * Copy is a first draft — refine freely; keep ids stable.
 */

export interface TestSpec {
	id: string;
	family: string;
	name: string;
	/** What misbehaviour the test is designed to catch. */
	threat: string;
	/** What we actually send and measure. */
	how: string;
	/** The statistic compared between reference and plan. */
	signal: string;
	/** What a pass does NOT establish. */
	limitation: string;
}

export const FAMILIES: Record<string, string> = {
	model_identity: 'Model identity',
	long_context: 'Long context',
	tool_use: 'Tool use',
	accounting: 'Accounting',
	api_compliance: 'API compliance',
	reasoning: 'Reasoning',
	capability: 'Capability',
	performance: 'Performance'
};

export const TESTS: TestSpec[] = [
	{
		id: 'arithmetic',
		family: 'model_identity',
		name: 'Long-multiplication accuracy',
		threat:
			'Aggressive weight quantization (e.g. INT4) served in place of the reference precision.',
		how: 'A fixed panel of multi-digit multiplications at temperature 0, scored digit by digit against the exact product.',
		signal:
			'Per-digit accuracy, plan vs official API; two-sided test on the difference in proportions.',
		limitation:
			'Mild quantization (FP8) often leaves arithmetic intact; a pass does not prove full precision.'
	},
	{
		id: 'rollout_prefix',
		family: 'model_identity',
		name: 'Greedy rollout prefix',
		threat: 'A different (cheaper or older) model answering under the advertised model name.',
		how: 'Long, tightly specified coding tasks at temperature 0, sampled several times on each side; we measure how many leading characters plan and reference completions share.',
		signal:
			'Mean cross-endpoint common prefix divided by each side’s own same-endpoint prefix (1.0 means indistinguishable).',
		limitation:
			'Non-deterministic batching makes T=0 outputs drift even on the official API, so only large gaps are meaningful.'
	},
	{
		id: 'entropy',
		family: 'model_identity',
		name: 'First-word entropy',
		threat: 'Altered sampling: clamped temperature, modified top-p, or a distilled substitute.',
		how: 'Repeated samples of the same open-ended coding prompts at temperature 1; we collect the distribution of first words.',
		signal: 'Rényi-2 (collision) entropy ratio plan/reference per prompt; flagged beyond ±15%.',
		limitation: 'Insensitive to changes that preserve the shape of the distribution.'
	},
	{
		id: 'needle_single',
		family: 'long_context',
		name: 'Single needle, length × depth',
		threat: 'Silent context truncation below the advertised window.',
		how: 'One fact hidden at varying depths in filler documents of increasing length; the model must retrieve it.',
		signal:
			'Retrieval accuracy across the length × depth grid; we look for a cliff the reference does not show.',
		limitation: 'Detects truncation, not subtler long-range degradation.'
	},
	{
		id: 'needle_multi',
		family: 'long_context',
		name: 'Multi-needle curvature',
		threat: 'KV-cache quantization or sparse attention that degrades mid-context recall.',
		how: 'Several facts spread through a long context; recall is scored by position.',
		signal: 'Curvature of the recall-by-position “smile” relative to the reference.',
		limitation: 'The smile varies by prompt; small panels give wide confidence intervals.'
	},
	{
		id: 'needle_aggregation',
		family: 'long_context',
		name: 'Needle aggregation',
		threat: 'Truncation that masquerades as a reasoning error.',
		how: 'Numbers scattered through a long context; the model must count them and report their sum.',
		signal:
			'Count accuracy vs sum accuracy — a wrong count points to truncation, a wrong sum to arithmetic.',
		limitation: 'Requires both endpoints to follow the output format reliably.'
	},
	{
		id: 'tool_calls',
		family: 'tool_use',
		name: 'Tool-call fidelity',
		threat:
			'Broken or degraded function calling (a known symptom of mis-served open-weight models).',
		how: 'Agentic prompts with JSON-schema tools, in the style of Kimi’s Vendor Verifier.',
		signal: 'Schema-valid tool-call rate and finish_reason agreement with the reference.',
		limitation: 'Covers single-turn calls; long multi-step agent loops are not exercised.'
	},
	{
		id: 'token_accounting',
		family: 'accounting',
		name: 'Token accounting',
		threat: 'Hidden system-prompt injection or inflated usage counts that drain quota faster.',
		how: 'Byte-identical requests to plan and reference; we compare reported usage.',
		signal: 'prompt_tokens (and completion_tokens) delta vs the official API for the same input.',
		limitation: 'Plans that do not return usage fields are reported as inconclusive.'
	},
	{
		id: 'param_compliance',
		family: 'api_compliance',
		name: 'Parameter compliance',
		threat: 'Request parameters silently ignored or overridden.',
		how: 'Requests that set max_tokens, stop sequences, JSON mode and temperature extremes, plus one ~10k-token reply that must not be cut short.',
		signal: 'Share of responses that honour each parameter.',
		limitation: 'Does not cover provider-specific extensions.'
	},
	{
		id: 'response_cache',
		family: 'api_compliance',
		name: 'Response cache detection',
		threat: 'Cached or replayed answers returned instead of fresh generations.',
		how: 'Prompts carrying a random nonce the model must echo; repeated near-identical requests.',
		signal: 'Rate of stale nonces or byte-identical replays at non-zero temperature.',
		limitation: 'Prompt-prefix caching (which is legitimate) is not flagged.'
	},
	{
		id: 'reasoning_budget',
		family: 'reasoning',
		name: 'Reasoning budget',
		threat: 'Thinking truncated or disabled to save compute.',
		how: 'Hard problems with thinking enabled; we record reasoning-token counts and final accuracy.',
		signal: 'Reasoning tokens per problem and accuracy, plan vs reference.',
		limitation: 'Reasoning-token reporting is inconsistent across vendors.'
	},
	{
		id: 'code_exec',
		family: 'capability',
		name: 'Executable coding tasks',
		threat: 'General quality loss on the workload the plan is sold for.',
		how: 'Small self-contained programming tasks; generated code is executed against unit tests in a sandbox.',
		signal: 'Unit-test pass rate, plan vs reference.',
		limitation: 'Small tasks; not representative of large-repository agentic work.'
	},
	{
		id: 'performance',
		family: 'performance',
		name: 'Throughput & latency',
		threat: 'Under-provisioned capacity: slow decoding, long queues, rate-limit errors.',
		how: 'Scheduled probe sessions with a fixed coding workload; each session records several streamed requests.',
		signal:
			'Output tokens per second (mean, p10), time to first token (mean, p90), and error rate.',
		limitation:
			'Measured from one region at sampled times of day; your experience may differ by location and load.'
	}
];

export const TEST_BY_ID = new Map(TESTS.map((t) => [t.id, t]));

export function familyLabel(family: string): string {
	return FAMILIES[family] ?? family.replace(/_/g, ' ');
}
