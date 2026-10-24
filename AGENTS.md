# Agent guidelines

Plan Watch audits flat-rate AI coding plans against the same provider's
pay-per-token API, with detectors validated in a GPU calibration lab. Read
`README.md` for the layout and commands, `docs/PLAN.md` for the research
plan.

## Stack

- **Python ≥ 3.11, uv.** One package, `src/planaudit/`, CLI `planaudit`.
  Deps: httpx, numpy, scipy, starlette/uvicorn, python-dotenv.
- **vLLM** runs in a separate venv (`~/.venvs/codingplans-lab`, override with
  `PLANAUDIT_VLLM`); the package only launches it as a subprocess.
- **Web:** SvelteKit 3 (config lives in `web/vite.config.ts`, imports use
  `#lib/…` with explicit `.ts` extensions), Svelte 5 runes, Tailwind 4,
  `adapter-static` → GitHub Pages at `/codingplans` (`BASE_PATH` overrides).
  The site reads `../data/*.json` at build time; it never calls an API.

## Commands

```bash
uv run pytest -q                 # Python tests (offline; fake server)
uv run ruff check src tests && uv run ruff format src tests
uv run planaudit selftest        # end-to-end probe check, no keys
uv run planaudit export          # refresh data/catalog.json after editing config/catalog.toml
cd web && npm run check && npm run lint && npm run build
```

## Rules for probes (`src/planaudit/probes/`)

1. **Deterministic panel.** `items()` depends only on the probe config; the
   `panel_hash` covers ids, sequencing and every request. Change prompts →
   the hash changes → old runs become incomparable (by design).
2. **No I/O in `compare()`.** Grading with side effects (running code) goes
   in `score()`, which the runner calls at collection time.
3. **Effect sign:** positive = target further from / worse than reference.
4. **Every probe has a lab story:** a corner-cut in `config/lab.toml` it is
   meant to catch, and a `default_margin` that the lab replaces with a
   calibrated one. A new probe must pass `tests/test_probes.py`-style
   honest-twin / degraded checks against `planaudit.fake`.
5. Sampled probes use `seed=FRESH_SEED`; prompts that must be new to the
   server use `Probe.RUN_NONCE`.

## Data

- `data/` is the public dataset and is committed. `var/` (raw runs, caches,
  logs) is local-only.
- Lab raw runs: `var/runs/lab/<family>/<variant>/<probe>.json.gz`; the
  runner skips anything whose panel hash still matches.

## Conventions

- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Never commit `.env` or API keys. Audit keys go in `.env` / GitHub secrets.
- Word results as measured differences, never as accusations.
- `CLAUDE.md` is a symlink to this file.
