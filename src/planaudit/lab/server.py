"""Start and stop a vLLM OpenAI server for one lab variant."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ..paths import LOGS
from .config import Lab, Variant


class VllmServer:
    def __init__(self, lab: Lab, variant: Variant, *, log_name: str):
        self.lab = lab
        self.variant = variant
        self.port = int(lab.engine["port"])
        self.log_path: Path = LOGS / "lab" / f"{log_name}.log"
        self.proc: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def command(self) -> list[str]:
        e = self.lab.engine
        return [
            self.lab.vllm,
            "serve",
            self.variant.model,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--served-model-name", e["served_model_name"],
            "--max-model-len", str(e["max_model_len"]),
            "--gpu-memory-utilization", str(e["gpu_memory_utilization"]),
            *e.get("args", []),
            *self.variant.args,
        ]  # fmt: skip

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "w")  # noqa: SIM115 - lives as long as the process
        cmd = self.command()
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        self.proc = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env={**os.environ, "VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1"},
        )  # fmt: skip
        deadline = time.monotonic() + float(self.lab.engine["startup_timeout_s"])
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                tail = self.log_path.read_text()[-3000:]
                raise RuntimeError(
                    f"vLLM exited ({self.proc.returncode}) for {self.variant.id}:\n{tail}"
                )
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(2)
        self.stop()
        raise TimeoutError(f"vLLM did not become healthy for {self.variant.id}")

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        os.killpg(self.proc.pid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()
        self.proc = None
        # Give the driver a moment to release device memory before the next start.
        time.sleep(3)

    def version(self) -> str:
        out = subprocess.run(
            [str(Path(self.lab.vllm).with_name("python")), "-c", "import vllm; print(vllm.__version__)"],
            capture_output=True, text=True,
        )  # fmt: skip
        return out.stdout.strip() or "unknown"

    def __enter__(self) -> VllmServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def gpu_name() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )  # fmt: skip
        return out.stdout.strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        print("warning: could not read GPU name", file=sys.stderr)
        return "unknown"
