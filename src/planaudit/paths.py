"""Repository locations. Everything else resolves paths through here."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("PLANAUDIT_ROOT", Path(__file__).resolve().parents[2]))
CONFIG = ROOT / "config"
DATA = ROOT / "data"  # published, versioned results (the public dataset)
VAR = Path(os.environ.get("PLANAUDIT_VAR", ROOT / "var"))  # local-only scratch
RUNS = VAR / "runs"  # raw per-endpoint run artifacts
CACHE = VAR / "cache"  # downloaded datasets
LOGS = VAR / "logs"


def load_env() -> None:
    """Load the repo-root .env without overriding variables already set."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
