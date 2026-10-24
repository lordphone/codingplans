"""Run an ASGI app on a background thread (tests, selftest, the lab proxy)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def background(app, port: int | None = None) -> Iterator[str]:
    """Serve `app` on 127.0.0.1; yields the OpenAI-style base URL (…/v1)."""
    port = port or free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        server.should_exit = True
        t.join(timeout=10)
