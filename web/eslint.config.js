import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import ts from 'typescript-eslint';

export default ts.config(
	{ ignores: ['build/', '.svelte-kit/', 'static/data/'] },
	js.configs.recommended,
	...ts.configs.recommended,
	...svelte.configs.recommended,
	prettier,
	...svelte.configs.prettier,
	{ languageOptions: { globals: { ...globals.browser, ...globals.node } } },
	{
		files: ['**/*.svelte', '**/*.svelte.ts'],
		languageOptions: { parserOptions: { parser: ts.parser } },
		// Internal links are already type-checked through resolve(); external
		// links (source repo, provider sites) are plain hrefs.
		rules: { 'svelte/no-navigation-without-resolve': ['error', { ignoreLinks: true }] }
	}
);
