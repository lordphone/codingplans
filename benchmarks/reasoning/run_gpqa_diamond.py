#!/usr/bin/env python3
"""
Run GPQA-Diamond (lm-eval, batch size 1).

**OpenAI-compatible** (default) — repo-root ``.env``:

  HF_TOKEN=...
  CODING_PLAN_API_KEY=...   # or LLM_API_KEY / OPENAI_API_KEY
  LLM_BASE_URL=https://.../v1
  LLM_MODEL=kimi-k2.5

**Anthropic Messages** (DashScope Coding intl proxy) — set ``LLM_PROVIDER=anthropic``:

  HF_TOKEN=...
  CODING_PLAN_API_KEY=...   # same key works; or ANTHROPIC_API_KEY / LLM_API_KEY
  LLM_MODEL=kimi-k2.5

Optional: ``ANTHROPIC_BASE_URL`` (default Coding intl:
``https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1/messages``).
For api.anthropic.com set ``ANTHROPIC_BASE_URL=https://api.anthropic.com/v1/messages``.

``LLM_TIMEOUT_S`` (default 120). CLI: ``--limit N``, ``--model``.

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
# DashScope Anthropic-compatible Messages (Coding Plan intl); must include ``/v1/messages``.
_DEFAULT_ANTHROPIC_BASE_URL = "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1/messages"
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


def _build_openai_compat_cmd(model: str, timeout: int) -> list[str]:
    api_key = _first_env("CODING_PLAN_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        sys.exit("Set CODING_PLAN_API_KEY, LLM_API_KEY, or OPENAI_API_KEY.")

    base = _first_env("LLM_BASE_URL", "CODING_PLAN_BASE_URL")
    if not base:
        sys.exit("Set LLM_BASE_URL (or CODING_PLAN_BASE_URL), e.g. https://coding-intl.dashscope.aliyuncs.com/v1")

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
    return [
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


def _build_anthropic_cmd(model: str, timeout: int) -> tuple[list[str], str]:
    key = _first_env("ANTHROPIC_API_KEY", "CODING_PLAN_API_KEY", "LLM_API_KEY")
    if not key:
        sys.exit(
            "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY, CODING_PLAN_API_KEY, or LLM_API_KEY."
        )

    base_url = _first_env("ANTHROPIC_BASE_URL") or _DEFAULT_ANTHROPIC_BASE_URL
    model_args = ",".join(
        [
            f"model={model}",
            f"base_url={base_url}",
            "max_gen_toks=2048",
            f"timeout={timeout}",
        ]
    )
    # Patched entry: DashScope returns thinking + text content blocks; stock lm-eval expects only text.
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
    return cmd, key


def main() -> int:
    _load_dotenv()

    p = argparse.ArgumentParser(description="Run GPQA-Diamond via .env + lm-eval.")
    p.add_argument("--model", "-m", default=None, help="Override LLM_MODEL")
    p.add_argument("--limit", "-L", type=int, default=None, metavar="N", help="Cap documents (testing)")
    args = p.parse_args()

    model = (args.model or "").strip() or _first_env("LLM_MODEL", "CODING_PLAN_MODEL")
    if not model:
        sys.exit("Set LLM_MODEL (or CODING_PLAN_MODEL), or pass --model.")

    try:
        timeout = int(os.environ.get("LLM_TIMEOUT_S", "120"))
    except ValueError:
        timeout = 120

    env = os.environ.copy()
    env.setdefault("LMEVAL_LOG_LEVEL", "ERROR")

    provider = _first_env("LLM_PROVIDER").lower()
    if provider == "anthropic":
        cmd, anthropic_key = _build_anthropic_cmd(model, timeout)
        env["ANTHROPIC_API_KEY"] = anthropic_key
    else:
        cmd = _build_openai_compat_cmd(model, timeout)

    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])

    return subprocess.run(cmd, env=env, cwd=str(_REPO_ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
