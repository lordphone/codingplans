"""Shared infrastructure for every benchmarks/fidelity/ test family.

Design rules — every test under fidelity/<family>/ follows them:

  1. **Single-endpoint runner.** Each test exposes a `run_<test>(endpoint, …)`
     function that hits exactly one endpoint and returns a `RunResult`. The
     test never knows about "reference" or "target"; that distinction lives
     in the comparison step only.
  2. **Self-describing artifacts.** A `RunResult` carries every piece of
     metadata the comparison step needs to verify two runs are comparable
     (schema version, panel id, prompt hash, sample counts, hyperparams).
  3. **Compare = pure function.** Each test exposes a
     `compare_<test>(reference, target) -> Report`. No HTTP, no file I/O,
     trivially unit-testable with synthetic `RunResult` instances.
  4. **Stealth.** Every runner uses `StealthChatClient` (rotated UA, jittered
     pacing) and a shuffled `make_schedule`. No batch APIs, ever.

This module is family-agnostic: it lives at fidelity/ root so
model_identity/ and long_context/ can all import the same plumbing. Each
family keeps its own prompts and per-family runs/ directory; the runner
CLIs pass their `runs_dir` to `write_run_artifacts` explicitly.

`client.py` and `targets.py` are siblings of this file.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from client import ChatRequest, ChatResponse, StealthChatClient
from targets import ENDPOINTS, Endpoint, get_endpoint

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "StealthChatClient",
    "Endpoint",
    "ENDPOINTS",
    "get_endpoint",
    "Call",
    "PromptItem",
    "PromptOutcome",
    "RunResult",
    "SCHEMA_VERSION",
    "assert_comparable",
    "common_prefix_chars",
    "digit_match_rate",
    "first_word",
    "fit_quadratic",
    "load_dotenv",
    "make_schedule",
    "mean_pairwise_prefix",
    "modal",
    "normalize_text",
    "panel_hash",
    "rank1_mass",
    "read_run_result",
    "renyi2_entropy",
    "safe_label",
    "shannon_entropy",
    "utc_stamp",
    "write_run_artifacts",
]

SCHEMA_VERSION = 1

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------


def load_dotenv() -> None:
    """Load repo-root .env if python-dotenv is installed. No-op otherwise."""
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        return
    _load(_REPO_ROOT / ".env")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_label(label: str) -> str:
    """Make an endpoint label safe for use in filenames."""
    out = []
    for ch in label:
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def modal(values: list[str]) -> tuple[str, int]:
    """Return (most-common value, its count). Empty list -> ('', 0)."""
    if not values:
        return "", 0
    val, count = Counter(values).most_common(1)[0]
    return val, count


def common_prefix_chars(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def shannon_entropy(values: list[str]) -> float:
    """Shannon entropy in bits over the empirical distribution of `values`."""
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    h = 0.0
    for c in counts.values():
        p = c / total
        h -= p * math.log2(p)
    return h


def renyi2_entropy(values: list[str]) -> float:
    """Renyi-2 (collision) entropy in bits: -log2(sum p_i^2).

    More sample-efficient than Shannon at moderate N: at N≈200 the plug-in
    Shannon estimator is biased ~0.3 bits, while Renyi-2 is much closer to
    the true value. This is the recommended primary statistic for the
    entropy test under text-only sampling (logprobs would dominate either)."""
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    p2 = sum((c / total) ** 2 for c in counts.values())
    if p2 <= 0.0:
        return 0.0
    return -math.log2(p2)


def rank1_mass(values: list[str]) -> float:
    """Probability mass of the modal value (rank-1 mass).

    A coarse but extremely sample-efficient quantization proxy: a flatter
    logit distribution lowers the modal probability. Detectable with ~200
    samples for a ~5% shift, vs ~10k for a clean Shannon estimate."""
    if not values:
        return 0.0
    _, top = Counter(values).most_common(1)[0]
    return top / len(values)


_OUTER_PUNCT_CHARS = " \t\r\n.,;:!?()[]{}\"'`*_~#>"


def first_word(text: str) -> str:
    """Normalized first whitespace-bounded token of `text`.

    Tokenizer-free proxy for the model's first emitted token. Lowercased
    and stripped of leading/trailing punctuation so `Redis.`, `"redis"`,
    and `redis` collapse to the same bucket — without that normalization,
    two endpoints serving the same weights look like they have different
    first-token distributions purely from a stray period or quote.
    """
    stripped = text.lstrip()
    if not stripped:
        return ""
    end = len(stripped)
    for i, ch in enumerate(stripped):
        if ch.isspace():
            end = i
            break
    word = stripped[:end].strip(_OUTER_PUNCT_CHARS)
    return word.casefold()


def digit_match_rate(parsed: int | None, expected: int) -> tuple[float, bool, bool]:
    """Per-digit accuracy plus first-digit and last-digit indicators.

    Returns (digit_accuracy, first_digit_ok, last_digit_ok). Digits are
    aligned right-to-left (zero-padded to the longer of the two strings),
    matching how arithmetic carries propagate. The first-digit indicator
    uses the leftmost digit of `expected` (the most-significant); the
    last-digit indicator uses the units digit. Sign mismatches collapse to
    (0.0, False, False).

    Why per-digit: research notes per-digit accuracy delivers ~10x the
    statistical sensitivity of all-or-nothing match, and lets us see
    *where* in the answer the model fails (last digits typically degrade
    first under quantization)."""
    if parsed is None:
        return 0.0, False, False
    if (parsed < 0) != (expected < 0):
        return 0.0, False, False
    p = str(abs(parsed))
    e = str(abs(expected))
    width = max(len(p), len(e))
    p = p.rjust(width, "0")
    e = e.rjust(width, "0")
    matches = sum(1 for a, b in zip(p, e) if a == b)
    return matches / width, p[0] == e[0], p[-1] == e[-1]


def mean_pairwise_prefix(a_samples: list[str], b_samples: list[str]) -> float:
    """Mean common-prefix length across all (a, b) pairs in a_samples × b_samples.

    Used by the rollout-prefix test to compare two endpoints' completion
    distributions without collapsing each side to its modal pick. Modal-
    vs-modal singletons are dominated by batch noise; the full N×M cross-
    pair mean is the distributional statistic the literature recommends."""
    if not a_samples or not b_samples:
        return 0.0
    total = 0
    pairs = 0
    for a in a_samples:
        for b in b_samples:
            total += common_prefix_chars(a, b)
            pairs += 1
    return total / pairs if pairs else 0.0


_WS_RE = re.compile(r"\s+")
# Map "fancy" Unicode punctuation that providers' safety filters love to
# rewrite back to ASCII so prefix comparisons aren't fooled by an em-dash
# swap or a smart-quote substitution.
_PUNCT_FOLD = {
    ord("‘"): "'", ord("’"): "'", ord("‚"): "'", ord("‛"): "'",
    ord("“"): '"', ord("”"): '"', ord("„"): '"', ord("‟"): '"',
    ord("–"): "-", ord("—"): "-", ord("−"): "-",
    ord(" "): " ",
}


def normalize_text(s: str) -> str:
    """NFKC normalize, fold smart-quotes/dashes, collapse whitespace.

    Some providers run a post-processing or safety pass that rewrites
    rare punctuation; without normalization a strict character-level
    prefix-match would fire on those rewrites and look like a swap."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_PUNCT_FOLD)
    s = _WS_RE.sub(" ", s)
    return s


def fit_quadratic(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float]:
    """Closed-form least-squares fit of y = a + b*x + c*x**2.

    Returns (a, b, c). The curvature coefficient `c` is what we test for
    the multi-needle smile-shape: a smile at depth ∈ [0,1] has c < 0
    (peaks at the edges, dips in the middle). With ≥3 points and any
    spread in xs the 3x3 normal-equation system is well-conditioned;
    raises ValueError on degenerate input."""
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs and ys must be the same length")
    if n < 3:
        raise ValueError("need at least 3 points to fit a quadratic")
    sx = sum(xs)
    sx2 = sum(x * x for x in xs)
    sx3 = sum(x ** 3 for x in xs)
    sx4 = sum(x ** 4 for x in xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2y = sum(x * x * y for x, y in zip(xs, ys))
    # Solve 3x3 normal equations via Gaussian elimination with partial pivot.
    m = [
        [float(n), sx, sx2, sy],
        [sx, sx2, sx3, sxy],
        [sx2, sx3, sx4, sx2y],
    ]
    for i in range(3):
        pivot = i
        for k in range(i + 1, 3):
            if abs(m[k][i]) > abs(m[pivot][i]):
                pivot = k
        if pivot != i:
            m[i], m[pivot] = m[pivot], m[i]
        if m[i][i] == 0.0:
            raise ValueError("singular matrix in fit_quadratic")
        for k in range(i + 1, 3):
            factor = m[k][i] / m[i][i]
            for j in range(i, 4):
                m[k][j] -= factor * m[i][j]
    c = m[2][3] / m[2][2]
    b = (m[1][3] - m[1][2] * c) / m[1][1]
    a = (m[0][3] - m[0][1] * b - m[0][2] * c) / m[0][0]
    return a, b, c


# ---------------------------------------------------------------------------
# Prompt panels & schedules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptItem:
    """One prompt slot in a panel.

    `messages` is the full chat array (system + user + ...). Tests pass it
    straight to ChatRequest. `meta` carries free-form per-test data
    (e.g. expected answer for arithmetic items)."""

    name: str
    messages: tuple[dict[str, str], ...]
    meta: dict | None = None


@dataclass(frozen=True)
class Call:
    prompt_idx: int
    sample_idx: int


def make_schedule(
    panel_size: int,
    n_samples: int,
    *,
    seed: int | None = None,
) -> list[Call]:
    """Build a shuffled schedule of (prompt_idx, sample_idx) calls.

    Single-endpoint by design — one `RunResult` covers exactly one endpoint.
    Comparison joins two artifacts. Shuffling the schedule keeps the wire
    pattern from looking like "same prompt N times in a row."
    """
    rng = random.Random(seed)
    calls = [Call(p, k) for p in range(panel_size) for k in range(n_samples)]
    rng.shuffle(calls)
    return calls


def panel_hash(panel: Sequence[PromptItem]) -> str:
    """Stable sha256 over the canonical serialization of a prompt panel.

    Two runs are only comparable when their `panel_hash` matches. Any change
    to a prompt (even whitespace) changes the hash and forces a rerun.
    """
    h = hashlib.sha256()
    for item in panel:
        # Use sort_keys so dict ordering inside `meta` doesn't change the hash.
        h.update(item.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(json.dumps(item.messages, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        h.update(b"\x00")
        h.update(json.dumps(item.meta, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        h.update(b"\xff")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Run artifact dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PromptOutcome:
    """Per-prompt outputs from one run.

    `completions` holds successful sampled completions, in the order they
    were drawn (after schedule shuffle). `errors` records any sample that
    failed (HTTP errors, timeouts, empty completions). `meta` carries the
    per-prompt metadata copied from the panel so comparison logic doesn't
    need to re-import the panel module.
    """

    prompt_idx: int
    name: str
    meta: dict | None
    completions: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


@dataclass
class RunResult:
    """The artifact a single test run produces against one endpoint.

    Compare two `RunResult`s with the relevant test's `compare_*()`
    function. Two runs are comparable iff:
        schema_version, test_name, panel_id, panel_size, prompt_hash,
        n_samples, max_tokens
    all match. (Sleep range and schedule seed deliberately do NOT affect
    comparability — they're stealth knobs, not measurement parameters.)
    """

    schema_version: int
    test_name: str
    panel_id: str
    panel_size: int
    prompt_hash: str
    n_samples: int
    max_tokens: int
    schedule_seed: int
    sleep_range_s: list[float]
    stamp_utc: str
    endpoint_label: str
    endpoint_model: str
    endpoint_base_url: str
    endpoint_extra_params: dict[str, Any]
    user_agent: str
    prompts: list[PromptOutcome]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "RunResult":
        prompts = [PromptOutcome(**p) for p in raw.get("prompts", [])]
        sleep_range = list(raw.get("sleep_range_s", []) or [])
        return cls(
            schema_version=int(raw["schema_version"]),
            test_name=str(raw["test_name"]),
            panel_id=str(raw["panel_id"]),
            panel_size=int(raw["panel_size"]),
            prompt_hash=str(raw["prompt_hash"]),
            n_samples=int(raw["n_samples"]),
            max_tokens=int(raw["max_tokens"]),
            schedule_seed=int(raw["schedule_seed"]),
            sleep_range_s=[float(x) for x in sleep_range],
            stamp_utc=str(raw["stamp_utc"]),
            endpoint_label=str(raw["endpoint_label"]),
            endpoint_model=str(raw["endpoint_model"]),
            endpoint_base_url=str(raw["endpoint_base_url"]),
            endpoint_extra_params=dict(raw.get("endpoint_extra_params") or {}),
            user_agent=str(raw.get("user_agent", "")),
            prompts=prompts,
        )


def assert_comparable(
    a: RunResult,
    b: RunResult,
    *,
    expected_test: str,
) -> None:
    """Raise ValueError if two runs cannot be meaningfully compared.

    Any mismatch in schema, test, panel, or sample counts is a hard stop —
    a comparison report against incompatible runs would mislead.
    """
    checks: list[tuple[bool, str]] = [
        (a.schema_version == SCHEMA_VERSION, f"reference schema_version={a.schema_version} (expected {SCHEMA_VERSION})"),
        (b.schema_version == SCHEMA_VERSION, f"target schema_version={b.schema_version} (expected {SCHEMA_VERSION})"),
        (a.test_name == expected_test, f"reference test_name={a.test_name!r} (expected {expected_test!r})"),
        (b.test_name == expected_test, f"target test_name={b.test_name!r} (expected {expected_test!r})"),
        (a.panel_id == b.panel_id, f"panel_id mismatch: {a.panel_id!r} vs {b.panel_id!r}"),
        (a.panel_size == b.panel_size, f"panel_size mismatch: {a.panel_size} vs {b.panel_size}"),
        (a.prompt_hash == b.prompt_hash, "prompt_hash mismatch (panel content differs between runs)"),
        (a.n_samples == b.n_samples, f"n_samples mismatch: {a.n_samples} vs {b.n_samples}"),
        (a.max_tokens == b.max_tokens, f"max_tokens mismatch: {a.max_tokens} vs {b.max_tokens}"),
    ]
    bad = [msg for ok, msg in checks if not ok]
    if bad:
        raise ValueError("runs not comparable:\n  - " + "\n  - ".join(bad))


# ---------------------------------------------------------------------------
# Artifact I/O
# ---------------------------------------------------------------------------


def write_run_artifacts(
    result: RunResult,
    raw_rows: Iterable[dict],
    *,
    runs_dir: Path,
) -> tuple[Path, Path]:
    """Write a run's `.summary.json` (the RunResult) and `.jsonl` (per-call
    forensic log) under `runs_dir`. Returns (summary_path, jsonl_path).

    Each test family chooses its own `runs_dir` (typically a sibling of the
    test scripts) so artifacts stay scoped to the family that produced them.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    base = runs_dir / f"{result.stamp_utc}_{safe_label(result.endpoint_label)}_{result.test_name}"
    summary_path = Path(f"{base}.summary.json")
    jsonl_path = Path(f"{base}.jsonl")

    summary_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in raw_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return summary_path, jsonl_path


def read_run_result(path: Path) -> RunResult:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunResult.from_dict(raw)
