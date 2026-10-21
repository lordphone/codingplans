# web — Coding Plan Comparison

Static SvelteKit (Svelte 5 runes) site, prerendered at build time and deployed to GitHub Pages.

```sh
npm install
npm run dev                                   # uses web/.env if present
PUBLIC_DATA_SOURCE=fixtures npm run dev       # sample data + banner
npm run check && npm run lint
BASE_PATH=/codingplans npm run build          # → build/
npm run preview
```

Environment (all public; see `.env.example`):

| Variable                   | Purpose                                                        |
| -------------------------- | -------------------------------------------------------------- |
| `PUBLIC_SUPABASE_URL`      | Supabase project URL (read at build time only)                 |
| `PUBLIC_SUPABASE_ANON_KEY` | anon / publishable key (RLS: SELECT only)                      |
| `PUBLIC_DATA_SOURCE`       | `fixtures` → build from `src/lib/data/fixtures.ts` (sample)    |
| `BASE_PATH`                | path prefix, e.g. `/codingplans` for GitHub Pages (CI sets it) |

Without Supabase variables (and not in fixtures mode) the build succeeds with empty states.
A Supabase error during build fails the build.

Layout: data access lives in `src/lib/data/` (`index.server.ts` is the only entry point pages use),
UI primitives in `src/lib/components/`, methodology copy in `src/lib/content/tests.ts`,
design tokens in `src/app.css` (mirrors `../DESIGN.md`).
