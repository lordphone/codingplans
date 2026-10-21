"""Run model-written Python against hidden tests in a throwaway subprocess.

Isolation is best-effort, not a security boundary: an isolated interpreter
(`-I`), an empty temp working directory, a scrubbed environment (no API
keys), CPU-time / memory / file-size rlimits and a wall-clock timeout. It does
NOT block network access. Run code_exec audits on an ephemeral CI runner (the
GitHub workflow does) or inside a container when running locally.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ExecResult", "extract_code", "run_tests"]

_FENCE_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(content: str) -> str:
    """The longest fenced code block, or the whole reply if there is none."""
    blocks = _FENCE_RE.findall(content or "")
    if blocks:
        return max(blocks, key=len)
    return content or ""


@dataclass
class ExecResult:
    passed: bool
    outcome: str  # pass | assertion | error | timeout | no_code
    detail: str


def _limits() -> None:  # pragma: no cover - runs in the child
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        except (ValueError, OSError):
            pass  # macOS does not support RLIMIT_AS
    except ImportError:
        pass


def run_tests(code: str, tests: str, *, timeout_s: float = 20.0) -> ExecResult:
    if not code.strip():
        return ExecResult(False, "no_code", "")
    program = f"{code}\n\n# --- hidden tests ---\n{tests}\nprint('__ALL_TESTS_PASSED__')\n"
    with tempfile.TemporaryDirectory(prefix="code_exec_") as tmp:
        path = Path(tmp) / "solution.py"
        path.write_text(program, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(path)],
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=_limits if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(False, "timeout", f">{timeout_s}s")
    if proc.returncode == 0 and "__ALL_TESTS_PASSED__" in proc.stdout:
        return ExecResult(True, "pass", "")
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
    outcome = "assertion" if "AssertionError" in (proc.stderr or "") else "error"
    return ExecResult(False, outcome, tail[0][:300])
