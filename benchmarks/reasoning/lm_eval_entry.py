"""
Patch Anthropic Messages parsing for DashScope (content may include thinking blocks), then run lm-eval CLI.

Used by run_gpqa_diamond.py for ``LLM_PROVIDER=anthropic`` (not ``python -m lm_eval`` directly).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _patch_anthropic_parse() -> None:
    from lm_eval.models import anthropic_llms as m

    def parse_generations(self, outputs, **kwargs):  # noqa: ANN001
        res: list[str] = []
        if not isinstance(outputs, list):
            outputs = [outputs]
        for out in outputs:
            parts: list[str] = []
            for block in out.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and "text" in block:
                    parts.append(block["text"])
            res.append("".join(parts))
        return res

    m.AnthropicChat.parse_generations = parse_generations  # type: ignore[method-assign]


def main() -> None:
    _patch_anthropic_parse()
    from lm_eval.__main__ import cli_evaluate

    cli_evaluate()


if __name__ == "__main__":
    main()
