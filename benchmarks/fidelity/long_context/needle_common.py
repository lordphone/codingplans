"""Shared infrastructure for long_context/ needle-in-haystack fidelity tests.

Three tests live in this family — single-needle, multi-needle, and
aggregation — and they all share the same plumbing:

  * deterministic procedural Python-shaped filler generation,
  * insertion of one or more "needle" facts at specified depths inside that
    filler, snapped to line boundaries so the surrounding code still parses
    visually,
  * grid-sweep helpers to enumerate (length, depth) cells,
  * the standard fidelity test_*.py shape (single-endpoint runner that
    returns a RunResult; pure compare function over two RunResults).

Why procedural filler instead of bundling real source code:
  * Two run artifacts only compare cleanly when their panel_hash matches.
    A procedural generator with a fixed seed gives the same bytes on every
    machine, including CI runners with different filesystems and locales.
  * Bundling a real corpus would also raise licensing questions and bloat
    the repo. We can scale to any context length on demand.
  * The generator emits Python-shaped tokens (imports, def, class,
    docstrings, comments, type hints), so the surrounding context still
    looks like code to the model — needles read as the only "fact-shaped"
    lines in a sea of plausible Python.

Filler determinism across lengths:
  * Filler at length L is always a prefix of filler at length 2L. We extend
    the stream by emitting blocks; we never re-roll earlier ones. That
    means a single (filler_seed,) tuple fully specifies the underlying
    haystack, and a (lengths, depths, filler_seed) tuple fully specifies
    the panel.

Schedule shuffling note:
  * Each test still uses the shared `make_schedule()` to randomize the
    order of (prompt_idx, sample_idx) calls, so a vendor watching the wire
    sees an interleaved sweep — not "all length-1024 prompts, then all
    length-2048 prompts in a row," which would be a giveaway.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_HERE = Path(__file__).resolve().parent
_FIDELITY_DIR = _HERE.parent
if str(_FIDELITY_DIR) not in sys.path:
    sys.path.insert(0, str(_FIDELITY_DIR))

from common import PromptItem  # noqa: E402

__all__ = [
    "FILLER_CORPUS_VERSION",
    "GridCell",
    "MultiCell",
    "AggregationCell",
    "generate_filler",
    "insert_at_depth",
    "insert_many_at_depths",
    "build_single_needle_messages",
    "build_multi_needle_messages",
    "build_aggregation_messages",
    "make_length_depth_grid",
    "format_panel_signature",
]


# Bump this when the procedural generator's byte-for-byte output for a
# given seed changes. Old artifacts then become non-comparable to new ones,
# which is the right outcome — the haystack itself is part of the panel.
FILLER_CORPUS_VERSION = "v1"


# ---------------------------------------------------------------------------
# Procedural Python-shaped filler generator
# ---------------------------------------------------------------------------
#
# A model trained on real code treats filler differently depending on how
# token-statistics-similar it is to real code. Pure random characters or
# Lorem-ipsum prose would be obviously not-code and give the model an easy
# heuristic ("ignore all the noise"). We mirror real Python's surface
# structure — imports, definitions, comments, type hints — using a small
# fixed lexicon, so the filler is plausible enough that a needle inserted
# as a code-style comment doesn't immediately stand out.

_VERBS = (
    "compute", "validate", "parse", "render", "load", "save", "transform",
    "encode", "decode", "fetch", "build", "merge", "split", "filter",
    "normalize", "serialize", "deserialize", "register", "lookup", "resolve",
    "format", "extract", "match", "apply", "ensure", "open", "close",
    "queue", "dispatch", "collect", "audit", "trace", "verify", "publish",
)

_NOUNS = (
    "request", "response", "user", "session", "token", "config", "registry",
    "context", "payload", "record", "item", "envelope", "message", "buffer",
    "header", "footer", "manifest", "snapshot", "fragment", "selector",
    "channel", "stream", "iterator", "cache", "result", "report", "policy",
    "snapshot", "ledger", "checkpoint", "shard", "lease", "binding",
)

_TYPES = (
    "str", "int", "float", "bool", "bytes", "dict[str, Any]", "list[str]",
    "list[int]", "tuple[int, ...]", "Path", "Iterable[str]", "Mapping[str, int]",
    "Optional[int]", "Optional[str]",
)

_IMPORTS = (
    "from __future__ import annotations",
    "from collections.abc import Iterable, Mapping, Sequence",
    "from dataclasses import dataclass, field",
    "from pathlib import Path",
    "from typing import Any, Optional",
    "import json",
    "import logging",
    "import re",
    "import textwrap",
    "import time",
)


def _ident(rng: random.Random) -> str:
    return f"{rng.choice(_VERBS)}_{rng.choice(_NOUNS)}"


def _emit_imports(rng: random.Random) -> str:
    """One-time preamble at the top of the filler stream."""
    picks = list(_IMPORTS)
    rng.shuffle(picks)
    return "\n".join(picks[: 3 + rng.randrange(4)]) + "\n\n"


def _emit_function(rng: random.Random) -> str:
    """A small Python function with a docstring, a couple of parameters,
    and a body of straight-line statements. Bodies don't need to be
    semantically meaningful — they just need to look like code."""
    name = _ident(rng)
    arity = 1 + rng.randrange(3)
    params = ", ".join(
        f"{_ident(rng)}: {rng.choice(_TYPES)}"
        for _ in range(arity)
    )
    ret_t = rng.choice(_TYPES)
    doc = f"{rng.choice(_VERBS).capitalize()} the {rng.choice(_NOUNS)} for the given {rng.choice(_NOUNS)}."
    body_lines = [
        f"    {_ident(rng)} = {rng.choice(_VERBS)}({_ident(rng)})",
        f"    if {_ident(rng)}.{rng.choice(_VERBS)}():",
        f"        return {_ident(rng)}",
        f"    return {_ident(rng)}({_ident(rng)})",
    ]
    return (
        f"def {name}({params}) -> {ret_t}:\n"
        f'    """{doc}"""\n'
        + "\n".join(body_lines)
        + "\n\n"
    )


def _emit_class(rng: random.Random) -> str:
    """A small dataclass-style class. We pick @dataclass because attribute
    declarations look distinctive enough that a model can't conflate them
    with the inserted needle's `# key = value` shape."""
    name = "".join(p.capitalize() for p in _ident(rng).split("_"))
    fields = []
    for _ in range(2 + rng.randrange(3)):
        fields.append(f"    {_ident(rng)}: {rng.choice(_TYPES)}")
    return (
        "@dataclass\n"
        f"class {name}:\n"
        + "\n".join(fields)
        + "\n\n"
    )


def _emit_comment(rng: random.Random) -> str:
    """A short comment block. Helps mask the inserted needle, which is
    itself comment-shaped."""
    lines = []
    for _ in range(1 + rng.randrange(3)):
        lines.append(
            f"# {rng.choice(_VERBS)} {rng.choice(_NOUNS)} via "
            f"{_ident(rng)} when the {rng.choice(_NOUNS)} is stale."
        )
    return "\n".join(lines) + "\n\n"


def generate_filler(target_chars: int, *, seed: int) -> str:
    """Procedurally generate Python-shaped filler text deterministic in
    `seed`. Returns at least `target_chars` characters; the caller may slice
    further if exact length matters.

    Same seed → same bytes; same seed at length 2L produces a string whose
    first L characters are identical to the L-length version (we never
    re-roll earlier blocks). That property is what lets the panel for a
    multi-length sweep stay coherent — different cells are prefixes of one
    canonical stream.
    """
    rng = random.Random(seed)
    parts: list[str] = [_emit_imports(rng)]
    chars = len(parts[0])
    while chars < target_chars:
        kind = rng.choice(("function", "function", "class", "comment", "function"))
        if kind == "function":
            block = _emit_function(rng)
        elif kind == "class":
            block = _emit_class(rng)
        else:
            block = _emit_comment(rng)
        parts.append(block)
        chars += len(block)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Needle insertion
# ---------------------------------------------------------------------------


def _snap_to_line_boundary(text: str, pos: int) -> int:
    """Move `pos` forward to the next newline. Inserting on a line boundary
    keeps the surrounding code visually intact and stops us from splitting
    a token (e.g. a function name) when the model scans for the needle."""
    if pos <= 0:
        return 0
    if pos >= len(text):
        return len(text)
    # Walk forward to the next newline; cap at end-of-string.
    while pos < len(text) and text[pos] != "\n":
        pos += 1
    return pos


def insert_at_depth(filler: str, needle_line: str, depth: float) -> str:
    """Insert `needle_line` (a single line, no trailing newline) at the
    first line boundary at-or-after fractional position `depth` in
    `filler`. `depth` is clamped to [0, 1].

    Snapping to a line boundary is what makes the inserted needle blend
    into the surrounding code — it lands between Python blocks rather than
    in the middle of an identifier.
    """
    depth = max(0.0, min(1.0, float(depth)))
    pos = _snap_to_line_boundary(filler, int(depth * len(filler)))
    return filler[:pos] + "\n" + needle_line + "\n" + filler[pos:]


def insert_many_at_depths(
    filler: str,
    needles: Iterable[tuple[str, float]],
) -> str:
    """Insert several (needle_line, depth) pairs into `filler`. Inserts
    proceed deepest-first so earlier insertion positions don't shift later
    ones.
    """
    items = sorted(needles, key=lambda nd: nd[1], reverse=True)
    out = filler
    for line, d in items:
        out = insert_at_depth(out, line, d)
    return out


# ---------------------------------------------------------------------------
# Prompt assembly (one chat-message tuple per test)
# ---------------------------------------------------------------------------
#
# Every test sends a single user turn — a short instruction + the haystack
# in a fenced code block. Putting the filler inside ``` ``` keeps streamed
# tokens visually separable and discourages the model from quoting the
# whole thing back. The instruction always says "reply with only X" so a
# parser on our end has a tight target.

_SINGLE_NEEDLE_INSTRUCTION = (
    "Below is a Python source file. Somewhere inside it there is exactly "
    "one comment line of the form `# UNLOCK_CODE = <value>`. Read carefully "
    "and reply with ONLY the value, nothing else — no quotes, no prose, no "
    "trailing punctuation."
)

_MULTI_NEEDLE_INSTRUCTION_TMPL = (
    "Below is a Python source file. Somewhere inside it there are exactly "
    "{k} comment lines of the form `# UNLOCK_CODE_<i> = <value>` where "
    "`<i>` is a small integer index (1..{k}). Read carefully and reply with "
    "one line per fact in the form `<i>=<value>` (no spaces, no prose), "
    "one per line, in any order. Output nothing else."
)

_AGGREGATION_INSTRUCTION_TMPL = (
    "Below is a Python source file. Scattered throughout it there are "
    "exactly {m} comment lines of the form `# COUNT_VALUE = <integer>`. "
    "Each integer is positive. Read carefully and reply with ONLY the "
    "SUM of those integers as a single decimal integer — no commas, no "
    "prose, no trailing punctuation."
)


def build_single_needle_messages(filler: str) -> tuple[dict[str, str], ...]:
    user = (
        f"{_SINGLE_NEEDLE_INSTRUCTION}\n\n```python\n{filler}\n```"
    )
    return ({"role": "user", "content": user},)


def build_multi_needle_messages(filler: str, k: int) -> tuple[dict[str, str], ...]:
    user = (
        f"{_MULTI_NEEDLE_INSTRUCTION_TMPL.format(k=k)}\n\n"
        f"```python\n{filler}\n```"
    )
    return ({"role": "user", "content": user},)


def build_aggregation_messages(filler: str, m: int) -> tuple[dict[str, str], ...]:
    user = (
        f"{_AGGREGATION_INSTRUCTION_TMPL.format(m=m)}\n\n"
        f"```python\n{filler}\n```"
    )
    return ({"role": "user", "content": user},)


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridCell:
    """One cell of the single-needle 2D sweep."""

    length_chars: int
    depth: float
    needle_value: str  # the secret payload the model must echo back


@dataclass(frozen=True)
class MultiCell:
    """One panel item for the multi-needle test: K needles at K depths
    inside a filler of a given length."""

    length_chars: int
    needles: tuple[tuple[int, float, str], ...]  # (idx, depth, value)


@dataclass(frozen=True)
class AggregationCell:
    """One panel item for the aggregation test: M scattered integer values
    inside a filler of a given length."""

    length_chars: int
    values: tuple[tuple[float, int], ...]  # (depth, integer)
    expected_sum: int
    expected_count: int


def make_length_depth_grid(
    lengths: Iterable[int],
    depths: Iterable[float],
) -> list[tuple[int, float]]:
    """Cartesian product of lengths × depths.

    The single-needle test uses this directly; multi-needle and aggregation
    use only the lengths column (their "depth" axis is internal — many
    facts at many depths inside a single prompt)."""
    return [(int(L), float(d)) for L in lengths for d in depths]


def format_panel_signature(*parts: object) -> str:
    """Stable, human-readable suffix for panel_id strings. Stringifies each
    part via repr-ish coercion and joins with `_`. We use this in panel_id
    so two artifacts with different grids fail `assert_comparable` early
    with an obvious "panel_id mismatch" message."""
    out: list[str] = []
    for p in parts:
        if isinstance(p, (list, tuple)):
            out.append("-".join(format_panel_signature(x) for x in p))
        elif isinstance(p, float):
            out.append(f"{p:g}")
        else:
            out.append(str(p))
    return "_".join(out)
