#!/usr/bin/env python3
"""
Run GPQA-Diamond (lm-eval, batch size 1) against your OpenAI-compatible API.

Put in repo-root ``.env`` (or export):

  HF_TOKEN=...                         # Hugging Face (gated GPQA dataset)
  CODING_PLAN_API_KEY=...              # or LLM_API_KEY / OPENAI_API_KEY
  LLM_BASE_URL=https://.../v1          # no /chat/completions suffix
  LLM_MODEL=glm-5                      # provider model id

Optional env: ``LLM_TIMEOUT_S`` (default 120). Optional CLI: ``--limit N``, ``--model`` overrides ``LLM_MODEL``.

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
_TOKENIZER = "Qwen/Qwen2.5-7B-Instruct"


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

    p = argparse.ArgumentParser(description="Run GPQA-Diamond via .env + lm-eval.")
    p.add_argument("--model", "-m", default=None, help="Override LLM_MODEL")
    p.add_argument("--limit", "-L", type=int, default=None, metavar="N", help="Cap documents (testing)")
    args = p.parse_args()

    api_key = _first_env("CODING_PLAN_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        sys.exit("Set CODING_PLAN_API_KEY, LLM_API_KEY, or OPENAI_API_KEY.")

    base = _first_env("LLM_BASE_URL", "CODING_PLAN_BASE_URL")
    if not base:
        sys.exit("Set LLM_BASE_URL (or CODING_PLAN_BASE_URL), e.g. https://coding-intl.dashscope.aliyuncs.com/v1")

    model = (args.model or "").strip() or _first_env("LLM_MODEL", "CODING_PLAN_MODEL")
    if not model:
        sys.exit("Set LLM_MODEL (or CODING_PLAN_MODEL), or pass --model.")

    try:
        timeout = int(os.environ.get("LLM_TIMEOUT_S", "120"))
    except ValueError:
        timeout = 120

    chat_url = base.rstrip("/") + "/chat/completions"
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
