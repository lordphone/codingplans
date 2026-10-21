export const SITE = {
	name: 'Coding Plan Comparison',
	wordmark: 'Codingplans',
	version: 'v0.1 alpha',
	repo: 'https://github.com/lordphone/codingplans',
	tagline:
		'Independent audits of AI coding subscriptions against the official API for the same model: speed, and whether you get the model you pay for.'
} as const;

export const IS_SAMPLE = __DATA_SOURCE__ === 'fixtures';
export const BUILD_TIME = __BUILD_TIME__;
