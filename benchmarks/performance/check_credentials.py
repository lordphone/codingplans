#!/usr/bin/env python3
"""
Verify API keys for benchmarks/providers.json (loads repo-root .env via python-dotenv).

Does not print secrets. Use instead of raw curl when .env is your source of truth.

  python benchmarks/performance/check_credentials.py
  python benchmarks/performance/check_credentials.py -p alibaba-cloud-model-studio-coding-plan
  python benchmarks/performance/check_credentials.py --thinking   # adds enable_thinking (Qwen-style)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROVIDERS_JSON = _REPO_ROOT / "benchmarks" / "providers.json"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env")


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is not None and v.strip():
        return v.strip()
    return None


def _message_from_completion(resp: dict[str, Any]) -> tuple[str, str | None]:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return "", None
    c = msg.get("content")
    r = msg.get("reasoning_content")
    c_str = c if isinstance(c, str) else ""
    r_str = r if isinstance(r, str) and r else None
    return c_str, r_str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify providers.json credentials (loads repo-root .env; never prints keys)",
    )
    parser.add_argument(
        "--provider",
        "-p",
        metavar="ID",
        help="Only check this provider id (slug from JSON)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, metavar="SEC")
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Send enable_thinking=true and thinking_budget=512 (for models that support it)",
    )
    args = parser.parse_args()
    _load_dotenv()

    if not PROVIDERS_JSON.is_file():
        print(f"Missing {PROVIDERS_JSON}", file=sys.stderr)
        return 1

    try:
        data = json.loads(PROVIDERS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1

    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        print('providers.json must contain a non-empty "providers" array', file=sys.stderr)
        return 1

    exit_code = 0
    for p in providers:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if args.provider and str(pid) != args.provider:
            continue
        base_url = str(p.get("base_url") or "").rstrip("/")
        key_env = p.get("api_key_env")
        models = p.get("models")
        if not pid or not base_url or not key_env:
            print(f"[{pid or '?'}] skip: missing id, base_url, or api_key_env", file=sys.stderr)
            exit_code = 1
            continue
        if not isinstance(models, list) or not models:
            print(f'[{pid}] skip: no models[]', file=sys.stderr)
            exit_code = 1
            continue

        api_key = _env(str(key_env))
        if not api_key:
            print(
                f"[{pid}] FAIL: {key_env} is not set (use repo-root .env or export the variable)",
                file=sys.stderr,
            )
            exit_code = 1
            continue

        model = str(models[0])
        url = f"{base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 16,
            "stream": False,
        }
        if args.thinking:
            body["enable_thinking"] = True
            body["thinking_budget"] = 512
        raw_extra = p.get("extra_params")
        if isinstance(raw_extra, dict):
            body.update(raw_extra)

        print(f"[{pid}] POST …/chat/completions model={model!r} …", end=" ", flush=True)
        try:
            r = httpx.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=args.timeout,
            )
        except httpx.RequestError as e:
            print(f"FAIL network: {e}", file=sys.stderr)
            exit_code = 1
            continue

        if r.status_code != 200:
            print(f"FAIL HTTP {r.status_code}", file=sys.stderr)
            try:
                err = r.json()
                print(f"       {err}", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"       {r.text[:400]}", file=sys.stderr)
            exit_code = 1
            continue

        try:
            payload = r.json()
        except json.JSONDecodeError:
            print("FAIL non-JSON response", file=sys.stderr)
            exit_code = 1
            continue

        content, reasoning = _message_from_completion(payload)
        note = ""
        if reasoning is not None:
            note = f" reasoning_chars={len(reasoning)}"
        elif args.thinking:
            note = " (no reasoning_content on this non-stream response)"
        print(f"OK content_chars={len(content)}{note}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
