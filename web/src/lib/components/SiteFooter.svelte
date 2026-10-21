<script lang="ts">
	import { resolve } from '$app/paths';
	import { fmtDateTime } from '$lib/format';
	import { BUILD_TIME, IS_SAMPLE, SITE } from '$lib/site';
</script>

<footer class="mt-24 border-t border-border bg-panel">
	<div
		class="mx-auto grid max-w-7xl gap-8 px-4 py-10 text-sm sm:px-6 md:grid-cols-[2fr_1fr_1fr] lg:px-12"
	>
		<div class="max-w-md">
			<p class="text-wordmark text-primary">{SITE.wordmark}</p>
			<p class="mt-3 text-muted">
				Independent, read-only measurements. Not affiliated with any provider listed. Results are
				statistical drift signals, not proof of intent — see the methodology.
			</p>
		</div>
		<div>
			<p class="text-eyebrow text-muted">Site</p>
			<ul class="mt-3 space-y-2">
				<li><a class="link" href={resolve('/')}>Directory</a></li>
				<li><a class="link" href={resolve('/benchmarks/')}>Benchmarks</a></li>
				<li><a class="link" href={resolve('/methodology/')}>Methodology</a></li>
			</ul>
		</div>
		<div>
			<p class="text-eyebrow text-muted">Build</p>
			<ul class="mt-3 space-y-2 font-mono text-xs">
				<li>
					Data updated <time datetime={BUILD_TIME} class="text-primary"
						>{fmtDateTime(BUILD_TIME)}</time
					>
				</li>
				<li>Source: {IS_SAMPLE ? 'sample fixtures' : 'published measurements'}</li>
				<li>
					<a
						class="link"
						href="https://github.com/lordphone/codingplans"
						rel="noopener noreferrer"
						target="_blank">github.com/lordphone/codingplans ↗</a
					>
				</li>
			</ul>
		</div>
	</div>
</footer>
