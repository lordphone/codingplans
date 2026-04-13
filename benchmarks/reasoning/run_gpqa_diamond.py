#!/usr/bin/env python3
"""
Run GPQA-Diamond (lm-eval, batch size 1) against one OpenAI-compatible endpoint from
``benchmarks/providers.json`` (copy from ``providers.example.json``).

Needs: repo-root ``.env`` with ``HF_TOKEN`` and the provider's ``api_key_env`` (e.g. ``CODING_PLAN_API_KEY``).

Usage (from repo root):

  python benchmarks/reasoning/run_gpqa_diamond.py

Optional: ``--config``, ``--provider ID``, ``--model NAME``, ``--limit N``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "benchmarks" / "providers.json"
_TASK = "gpqa_diamond_cot_zeroshot"
# Chat template for lm-eval only; API still receives your real ``model`` id.
_TOKENIZER = "Qwen/Qwen2.5-7B-Instruct"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)


def _pick_endpoint(
    data: dict,
    *,
    provider_id: str | None,
    model_name: str | None,
) -> tuple[str, str, str, int]:
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        sys.exit('Config needs a non-empty "providers" array.')

    if provider_id:
        prov = next((p for p in providers if isinstance(p, dict) and p.get("id") == provider_id), None)
        if prov is None:
            sys.exit(f'No provider with id "{provider_id}".')
    else:
        prov = next((p for p in providers if isinstance(p, dict)), None)
        if prov is None:
            sys.exit("No valid provider object in config.")

    pid = str(prov.get("id", "?"))
    base_url = prov.get("base_url")
    key_env = prov.get("api_key_env")
    models = prov.get("models")
    if not base_url or not key_env:
        sys.exit(f'Provider "{pid}" needs base_url and api_key_env.')
    if not isinstance(models, list) or not models:
        sys.exit(f'Provider "{pid}" needs a non-empty models list.')

    api_key = os.environ.get(str(key_env), "").strip()
    if not api_key:
        sys.exit(f"Set {key_env} in your environment or .env file.")

    if model_name:
        if model_name not in [str(m) for m in models]:
            sys.exit(f'Model "{model_name}" not listed under provider "{pid}".')
        model = model_name
    else:
        model = str(models[0])

    chat_url = str(base_url).rstrip("/") + "/chat/completions"
    timeout = int(prov.get("timeout_s", data.get("timeout_s", 120)))
    return model, chat_url, api_key, timeout


def main() -> int:
    _load_dotenv()

    p = argparse.ArgumentParser(description="Run GPQA-Diamond via providers.json + lm-eval.")
    p.add_argument(
        "--config",
        "-c",
        default=str(_DEFAULT_CONFIG),
        help=f"JSON config (default: {_DEFAULT_CONFIG})",
    )
    p.add_argument("--provider", "-p", default=None, metavar="ID", help="Provider id (default: first)")
    p.add_argument("--model", "-m", default=None, metavar="NAME", help="Model name (default: first listed)")
    p.add_argument("--limit", "-L", type=int, default=None, metavar="N", help="Cap documents (testing)")
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = _REPO_ROOT / cfg_path
    if not cfg_path.is_file():
        sys.exit(f"Config not found: {cfg_path}\nCopy benchmarks/providers.example.json to benchmarks/providers.json")

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        sys.exit("Config must be a JSON object.")

    model, chat_url, api_key, timeout = _pick_endpoint(
        data, provider_id=args.provider, model_name=args.model
    )

    model_args = ",".join(
        [
            f"model={model}",
            f"base_url={chat_url}",
            f"auth_token={api_key}",
            "tokenized_requests=False",
            "tokenizer_backend=huggingface",
            f"tokenizer={_TOKENIZER}",
            "max_gen_toks=2048",
            f"timeout={timeout}",
        ]
    )

    cmd: list[str] = [
        sys.executable,
        "-m",
        "lm_eval",
        "run",
        "--model",
        "local-chat-completions",
        "--model_args",
        model_args,
        "--tasks",
        _TASK,
        "--batch_size",
        "1",
        "--gen_kwargs",
        "temperature=0",
        "--apply_chat_template",
    ]
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])

    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
