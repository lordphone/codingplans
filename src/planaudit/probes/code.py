"""Coding accuracy on HumanEval, graded by running the hidden unit tests.

Detects: general quality regression (quantization, swap, reasoning cuts).

Generated code runs in a sandbox: a `--network none` Docker container when
Docker is available, otherwise a resource-limited subprocess (no network
isolation; see `sandbox`). The dataset is fetched once from the Hugging Face
datasets server and cached under var/cache.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import cache
from typing import Any

import httpx

from ..client import Completion, Request
from ..paths import CACHE
from . import panels
from .accuracy import AccuracyProbe
from .base import Item

ROWS_URL = "https://datasets-server.huggingface.co/rows"
_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


@cache
def humaneval() -> list[dict[str, Any]]:
    path = CACHE / "humaneval.json"
    if not path.exists():
        rows: list[dict[str, Any]] = []
        with httpx.Client(timeout=60) as http:
            while len(rows) < 164:
                r = http.get(
                    ROWS_URL,
                    params={
                        "dataset": "openai/openai_humaneval",
                        "config": "openai_humaneval",
                        "split": "test",
                        "offset": len(rows),
                        "length": 100,
                    },
                )
                r.raise_for_status()
                batch = [x["row"] for x in r.json()["rows"]]
                if not batch:
                    break
                rows += batch
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))
    return json.loads(path.read_text())


def extract_program(prompt: str, completion: str, entry_point: str) -> str:
    blocks = _FENCE.findall(completion)
    code = max(blocks, key=len) if blocks else completion
    if f"def {entry_point}" in code:
        # Keep the prompt's imports; the model's code may rely on them.
        imports = "\n".join(ln for ln in prompt.splitlines() if ln.startswith(("import ", "from ")))
        return f"{imports}\n{code}"
    return prompt + code


def sandbox(program: str, timeout_s: float = 10.0) -> bool:
    """Run `program`; True iff it exits 0 within the timeout."""
    use_docker = os.environ.get("PLANAUDIT_SANDBOX", "auto")
    if use_docker == "auto":
        use_docker = "docker" if shutil.which("docker") and _docker_ok() else "process"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "prog.py")
        with open(path, "w") as f:
            f.write(program)
        if use_docker == "docker":
            cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--pids-limit",
                "64",
                "-v",
                f"{d}:/w:ro",
                _image(),
                "python",
                "-I",
                "/w/prog.py",
            ]
            timeout_s += 10  # container start-up
        else:
            cmd = [sys.executable, "-I", path]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_s,
                cwd=d,
                preexec_fn=_limits if use_docker != "docker" else None,
            )
        except subprocess.TimeoutExpired:
            return False
        return res.returncode == 0


@cache
def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _image() -> str:
    return os.environ.get("PLANAUDIT_SANDBOX_IMAGE", "python:3.12-slim")


def _limits() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    os.setsid()


class CodeProbe(AccuracyProbe):
    name = "code"
    title = "Coding tasks (HumanEval)"
    detects = "quality regression"
    default_margin = 0.05
    defaults = {"n_items": 164, "max_tokens": 768, "seed": 1}

    def items(self) -> list[Item]:
        rows = humaneval()[: self.cfg["n_items"]]
        out = []
        for row in rows:
            req = Request(
                messages=panels.user(
                    "Complete the following Python function. Reply with the complete "
                    "function in a single ```python code block and nothing else.\n\n"
                    + row["prompt"]
                ),
                max_tokens=self.cfg["max_tokens"],
                temperature=0.0,
            )
            tid = row["task_id"].replace("/", "_")
            out.append(Item(id=tid, requests=[req], meta={"task": row["task_id"]}))
        return out

    def score(self, item: Item, completion: Completion) -> dict[str, Any]:
        row = next(r for r in humaneval() if r["task_id"] == item.meta["task"])
        program = (
            extract_program(row["prompt"], completion.text, row["entry_point"])
            + "\n\n"
            + row["test"]
            + f"\n\ncheck({row['entry_point']})\n"
        )
        return {"correct": float(sandbox(program))}
