#!/usr/bin/env python3
"""
Run GPQA-Diamond through lm-evaluation-harness using sequential API calls (batch size 1).

Prerequisites
-------------
1. From repo root: ``pip install -r requirements.txt`` (same ``.venv`` as other benchmarks).
2. Hugging Face: the task pulls ``Idavidrein/gpqa`` (gated). Accept the license on the Hub,
   then ``huggingface-cli login`` or set ``HF_TOKEN`` (or ``HUGGING_FACE_HUB_TOKEN``).
   You can put it in the repo-root ``.env``; this script loads that file if ``python-dotenv`` is installed.
3. Model API key in the environment (e.g. ``OPENAI_API_KEY`` for ``openai-chat-completions``).

Examples
--------
  # Smoke test (no API calls; still needs HF access to download GPQA)
  python benchmarks/reasoning/run_gpqa_diamond.py --limit 1 --dry-run

  # OpenAI Chat Completions (CoT zero-shot; matches generate_until GPQA setup)
  export OPENAI_API_KEY=...
  export HF_TOKEN=...  # if not already logged in via CLI
  python benchmarks/reasoning/run_gpqa_diamond.py --model gpt-4o-mini

  # OpenAI-compatible base URL (LM Studio, LiteLLM proxy, etc.)
  python benchmarks/reasoning/run_gpqa_diamond.py \\
      --model-type local-chat-completions \\
      --model qwen2.5 \\
      --model-args 'base_url=http://127.0.0.1:1234/v1/chat/completions,tokenized_requests=False,tokenizer_backend=huggingface,tokenizer=Qwen/Qwen2.5-7B-Instruct' \\
      --auth-token sk-...

Note: ``openai-chat-completions`` does not support loglikelihood; use CoT / generative GPQA tasks,
not ``gpqa_diamond_zeroshot`` (multiple choice), with chat APIs. Default task is
``gpqa_diamond_cot_zeroshot``.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path


DEFAULT_TASK = "gpqa_diamond_cot_zeroshot"


def _load_repo_dotenv() -> None:
    """Load repo-root ``.env`` so ``HF_TOKEN`` / ``OPENAI_API_KEY`` work without manual export."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("Examples", 1)[0].strip())
    p.add_argument(
        "--model",
        "-m",
        default="gpt-4o-mini",
        help="Model id passed to lm-eval (e.g. gpt-4o-mini, claude-3-5-sonnet-20241022).",
    )
    p.add_argument(
        "--model-type",
        "-M",
        default="openai-chat-completions",
        help="lm-eval model type (default: openai-chat-completions).",
    )
    p.add_argument(
        "--model-args",
        "-a",
        default="",
        help="Extra lm-eval model_args as one shell-style string, e.g. "
        "'base_url=http://localhost:8000/v1/chat/completions,tokenized_requests=False'.",
    )
    p.add_argument(
        "--task",
        "-t",
        default=DEFAULT_TASK,
        help=f"lm-eval task name (default: {DEFAULT_TASK}).",
    )
    p.add_argument(
        "--limit",
        "-L",
        type=int,
        default=None,
        metavar="N",
        help="Only first N documents per task (testing only).",
    )
    p.add_argument(
        "--output-path",
        "-o",
        default="",
        help="lm-eval --output_path (dir or .json).",
    )
    p.add_argument(
        "--log-samples",
        "-s",
        action="store_true",
        help="Save model outputs (--log_samples).",
    )
    p.add_argument(
        "--gen-kwargs",
        default="temperature=0",
        help="Generation kwargs for lm-eval, e.g. temperature=0",
    )
    p.add_argument(
        "--no-apply-chat-template",
        action="store_true",
        help="Omit --apply_chat_template (not recommended for chat API models).",
    )
    p.add_argument(
        "--auth-token",
        default="",
        help="Appended as auth_token=... to model_args (OpenAI-compatible servers).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the lm-eval command and exit without running.",
    )
    return p


def _quote_cmd(argv: list[str]) -> str:
    return " ".join(shlex.quote(x) for x in argv)


def main() -> int:
    _load_repo_dotenv()
    args = _build_parser().parse_args()

    model_arg_parts = [f"model={args.model}", "max_gen_toks=2048"]
    if args.model_args.strip():
        model_arg_parts.append(args.model_args.strip())
    if args.auth_token.strip():
        model_arg_parts.append(f"auth_token={args.auth_token.strip()}")
    model_args_str = ",".join(model_arg_parts)

    cmd: list[str] = [
        sys.executable,
        "-m",
        "lm_eval",
        "run",
        "--model",
        args.model_type,
        "--model_args",
        model_args_str,
        "--tasks",
        args.task,
        "--batch_size",
        "1",
        "--gen_kwargs",
        args.gen_kwargs,
    ]
    if not args.no_apply_chat_template:
        cmd.append("--apply_chat_template")
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])
    if args.output_path:
        cmd.extend(["--output_path", args.output_path])
    if args.log_samples:
        cmd.append("--log_samples")

    log_cmd = _quote_cmd(cmd)
    if args.auth_token.strip():
        log_cmd = log_cmd.replace(args.auth_token.strip(), "<redacted>")
    print(log_cmd, file=sys.stderr)
    if args.dry_run:
        return 0

    import subprocess

    proc = subprocess.run(cmd)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
