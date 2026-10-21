#!/usr/bin/env python3
"""Preflight every endpoint in endpoints.json with one tiny request each.

Run this first after adding keys. For each endpoint it reports, without
printing secrets: key present, HTTP status, the model id the server says it
served (catches silent aliasing like glm-5.2 → glm-5.3), whether usage is
reported in the stream (token_accounting needs it), whether reasoning was
streamed with thinking on/off, and whether tool calls come back.

  python benchmarks/audit/preflight.py              # all endpoints
  python benchmarks/audit/preflight.py --endpoint glm5-alibaba
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIDELITY = _HERE.parent / "fidelity"
if str(_FIDELITY) not in sys.path:
    sys.path.insert(0, str(_FIDELITY))

from client import ChatRequest, StealthChatClient  # noqa: E402
from framework import load_dotenv  # noqa: E402
from targets import ENDPOINTS  # noqa: E402

_TOOL = ({
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"], "additionalProperties": False},
    },
},)


def check(slug: str) -> None:
    ep = ENDPOINTS[slug]
    print(f"\n{slug}  ({ep.role}, model={ep.model}, {ep.base_url})")
    if ep.api_key() is None:
        print(f"  key: {ep.api_key_env} MISSING")
        return
    print(f"  key: {ep.api_key_env} set")
    msgs = ({"role": "user", "content": "Reply with exactly: pong"},)
    with StealthChatClient(min_sleep_s=0.5, max_sleep_s=1.0) as client:
        for label, thinking in (("default", None), ("thinking off", False), ("thinking on", True)):
            if thinking is False and ep.thinking_off is None:
                print(f"  {label:<13} n/a (cannot disable thinking)")
                continue
            try:
                r = client.chat(ep, ChatRequest(messages=msgs, temperature=0.0, max_tokens=2048,
                                                thinking=thinking), allow_empty=True)
                print(f"  {label:<13} ok  served_model={r.served_model!r} "
                      f"usage={'yes' if r.prompt_tokens is not None else 'NO'} "
                      f"reasoning={'yes' if r.reasoning else 'no'} "
                      f"ttft={r.ttft_s or 0:.2f}s reply={r.content.strip()[:30]!r}")
            except Exception as e:  # noqa: BLE001
                print(f"  {label:<13} FAIL {type(e).__name__}: {str(e)[:200]}")
            client.pause()
        try:
            r = client.chat(ep, ChatRequest(
                messages=({"role": "user", "content": "Open README.md"},),
                temperature=0.6, max_tokens=1024, tools=_TOOL), allow_empty=True)
            names = [c.get("name") for c in r.tool_calls]
            print(f"  tools         {'ok ' + str(names) if names else 'NO tool call returned'}")
        except Exception as e:  # noqa: BLE001
            print(f"  tools         FAIL {type(e).__name__}: {str(e)[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", action="append", help="Endpoint slug (repeatable)")
    args = parser.parse_args()
    load_dotenv()
    for slug in args.endpoint or sorted(ENDPOINTS):
        if slug not in ENDPOINTS:
            print(f"unknown endpoint {slug!r}", file=sys.stderr)
            return 2
        check(slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
