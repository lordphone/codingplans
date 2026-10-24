# codingplans — Plan Watch

Independent audits of flat-rate AI coding plans. Each plan is compared with
**the same provider's own pay-per-token API** for the same model: identical
requests, sent side by side, then a battery of statistical probes asks whether
the plan serves the same thing — or a quantized, swapped, truncated,
cache-faking or throttled version of it.

Detectors are not trusted until they have been validated in a **calibration
lab**: a small open model served on a local GPU in known honest and
corner-cutting configurations, so detection rates, false-alarm rates and the
cost of each detection in requests are measured, not assumed.

```
config/catalog.toml ─┐                      ┌─► data/audits/…   ─┐
                     ├─► planaudit audit ───┤                    ├─► web/ (static site, GitHub Pages)
plan + official APIs ┘                      │                    │
config/lab.toml ─► planaudit lab run ─► var/runs/lab ─► planaudit lab analyze ─► data/lab/…
```

## Layout

| Path | What |
|---|---|
| `config/catalog.toml` | Providers, models, plans, endpoints, audit pairings: the single source of truth |
| `config/lab.toml` | Lab families (Qwen2.5 7B/3B/1.5B) and their honest / corner-cut variants |
| `src/planaudit/` | The Python package and `planaudit` CLI |
| `src/planaudit/probes/` | Detectors: `logprob`, `distribution`, `arithmetic`, `code`, `needle`, `cache`, `accounting`, `speed` |
| `src/planaudit/lab/` | vLLM server manager, adversary proxy, experiment runner, power analysis |
| `tests/` | pytest suite against a toy OpenAI-compatible server (no keys, no GPU) |
| `data/` | The published dataset; the website reads only this |
| `var/` | Local-only raw runs, caches, logs (git-ignored) |
| `web/` | SvelteKit 3 + Tailwind 4 static site |
| `docs/` | Project plan and research notes |

## Quick start

```bash
uv sync
uv run pytest -q              # offline test suite
uv run planaudit selftest     # each probe passes an honest twin and flags a degraded one
uv run planaudit catalog      # validate config, see which API keys are present
```

Website:

```bash
cd web && npm install && npm run dev
```

## Calibration lab (NVIDIA GPU)

vLLM lives in its own environment so its heavy dependencies never touch the
package:

```bash
uv venv ~/.venvs/codingplans-lab --python 3.12
VIRTUAL_ENV=~/.venvs/codingplans-lab uv pip install vllm
~/.venvs/codingplans-lab/bin/vllm download-kernels     # prebuilt FlashInfer kernels (no nvcc needed)
uv run planaudit lab run --family qwen2.5-7b           # resumable; ~5 min per variant on an RTX 5090
uv run planaudit lab analyze                           # margins + power curves -> data/lab/
```

To add a corner-cut, add a variant to `config/lab.toml`: engine-level cuts
are vLLM flags, gateway-level cuts go through the adversary proxy
(`proxy = { truncate_tokens = 8000 }`, `inject_system`, `phantom_cache`,
`clamp_max_tokens`, `delay_s`). To poke a variant by hand:
`uv run planaudit lab serve qwen2.5-7b int4-awq`.

## Auditing a plan

Needs keys for both sides of a pair (copy `.env.example` to `.env`).

```bash
uv run planaudit preflight                                   # one tiny call per endpoint with a key
uv run planaudit audit --all --dry-run                       # what would run, which keys are missing
uv run planaudit audit --plan zai-glm-coding-lite --tier quick --calibrate
```

Results are written to `data/audits/<plan>/<endpoint>/<date>_<tier>.json` and
`data/audits/index.json`; commit them to publish.

### Before you audit

Several plans' terms restrict automated or non-interactive use (see the
`tos_risk` / `tos_note` of each plan in `config/catalog.toml` and
`docs/research/landscape.md`). An account can be banned mid-study. Use paid
accounts that look like ordinary customers (never free credits from the
provider being audited), keep the `quick` tier for routine runs, and decide
per plan whether the risk is acceptable. The client sends an honest
`planaudit/<version>` User-Agent.

## How a verdict is reached

1. Both endpoints get the same panel in one shuffled, interleaved schedule.
2. Each probe produces an effect size (positive = plan further from / worse
   than the API) and a p-value.
3. p-values are Benjamini–Hochberg adjusted across the audit's probes.
4. A probe flags only if q < 0.05 **and** the effect exceeds its margin: the
   largest effect any honest serving variation produced in the lab, plus 25%
   (`--calibrate` also widens it by the API's own reference-vs-reference
   difference).

See `web/src/routes/method/` (rendered at `/method`) for the full method.

## License

MIT
