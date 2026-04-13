#!/usr/bin/env python3
"""
Run GPQA-Diamond (lm-eval, batch size 1) on Alibaba Coding Plan intl **Anthropic Messages** API.

Hardcoded in this file: model ``glm-5``, endpoint
``https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1/messages``.

Repo-root ``.env``:

  HF_TOKEN=...                 # Hugging Face (gated GPQA dataset)
  CODING_PLAN_API_KEY=...      # or ANTHROPIC_API_KEY / LLM_API_KEY (``x-api-key``)

Optional: ``LLM_TIMEOUT_S`` (default 120). Only CLI flag: ``--limit N`` (smoke tests).

Usage::

  python benchmarks/reasoning/run_gpqa_diamond.py
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK = "gpqa_diamond_cot_zeroshot"
_MODEL = "glm-5"
_ANTHROPIC_MESSAGES_URL = "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1/messages"
_LM_EVAL_ENTRY = _REPO_ROOT / "benchmarks" / "reasoning" / "lm_eval_entry.py"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)


def _first_env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return ""


def main() -> int:
    _load_dotenv()

    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--limit", type=int, default=None, metavar="N")
    args, unknown = p.parse_known_args()
    if unknown:
        sys.exit(f"Unknown arguments: {' '.join(unknown)}. Only --limit is supported.")

    key = _first_env("CODING_PLAN_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY")
    if not key:
        sys.exit("Set CODING_PLAN_API_KEY (or ANTHROPIC_API_KEY / LLM_API_KEY) in .env.")

    try:
        timeout = int(os.environ.get("LLM_TIMEOUT_S", "120"))
    except ValueError:
        timeout = 120

    model_args = ",".join(
        [
            f"model={_MODEL}",
            f"base_url={_ANTHROPIC_MESSAGES_URL}",
            "max_gen_toks=2048",
            f"timeout={timeout}",
        ]
    )

    cmd: list[str] = [
        sys.executable,
        str(_LM_EVAL_ENTRY),
        "run",
        "--model",
        "anthropic-chat-completions",
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

    env = os.environ.copy()
    env.setdefault("LMEVAL_LOG_LEVEL", "ERROR")
    env["ANTHROPIC_API_KEY"] = key

    return subprocess.run(cmd, env=env, cwd=str(_REPO_ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
