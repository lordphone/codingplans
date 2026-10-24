export const site = {
	name: 'Plan Watch',
	tagline: 'Independent audits of AI coding plans',
	description:
		'Do flat-rate AI coding plans serve the same model as the provider’s own pay-per-token API? We measure it, with detectors validated on known corner-cuts.',
	repo: 'https://github.com/lordphone/codingplans'
};

export const nav = [
	{ href: '/plans', label: 'Plans' },
	{ href: '/lab', label: 'Lab' },
	{ href: '/method', label: 'Method' },
	{ href: '/data', label: 'Data' }
] as const;
