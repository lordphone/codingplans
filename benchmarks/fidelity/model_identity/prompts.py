"""Prompt panels for the three v1 fidelity weight-signal benchmarks.

Three panels live here:

  * ROLLOUT_PROMPTS   — 20 deterministic-leaning long-output coding tasks
                       used by test_rollout_prefix.py (T=0).
  * ARITHMETIC_PROMPTS — 100 multiplications wrapped as natural unit-test
                        / fixture questions, with deterministic ground truth.
                        Used by test_arithmetic.py (T=0).
  * ENTROPY_PROMPTS    — 10 open-ended coder-flavored prompts used by
                        test_entropy.py (T=1) to estimate first-token entropy.

Each panel has a `panel_id` (`ROLLOUT_PANEL_ID` etc.). Two run artifacts are
only comparable if they share the same `panel_id` AND `prompt_hash`. Bump
the `_v1` suffix when changing prompt content to invalidate old runs cleanly.

Stealth notes:
  * Each prompt is phrased the way a real developer using Cursor / Claude Code
    / Copilot would phrase it. There is no "benchmark" framing, no "respond
    only with X for evaluation", no fenced answer tags, no obvious markers.
  * The three panels deliberately span common languages (Python, TypeScript,
    Go, SQL, JSON) so that, mixed with the StealthChatClient's rotating IDE
    User-Agents, the request stream over a single audit looks like an active
    polyglot coding session rather than an evaluation harness.
  * Arithmetic prompts are framed as "writing a unit-test fixture" because
    that is a real, common reason a developer would ask a model for the
    exact product of two large integers (and is the only natural framing
    that justifies an answer-only response).
"""

from __future__ import annotations

import random
from typing import List

from framework import PromptItem


# ---------------------------------------------------------------------------
# Shared system prompts (light, IDE-flavored, indistinguishable from real
# coding-tool system prompts).
# ---------------------------------------------------------------------------

_SYS_IDE = (
    "You are an AI coding assistant integrated into the user's code editor. "
    "Help with code generation, debugging, refactoring, and explanation. "
    "Provide concise, working code that follows the project's existing "
    "conventions. When the user asks for code only, return code only with no "
    "prose, no markdown fences, and no comments unless they ask for them."
)

_SYS_PAIR = (
    "You are a pair programming assistant. The developer shares code with you "
    "and you help write, review, and improve it. Lead with the most relevant "
    "code changes. Match the existing codebase patterns and conventions."
)


def _msgs(system: str, user: str) -> tuple[dict[str, str], ...]:
    return (
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    )


# ---------------------------------------------------------------------------
# Test 1 — Long deterministic rollout divergence (panel of 20)
# ---------------------------------------------------------------------------
#
# Each prompt asks for a long, structurally constrained output where there's
# essentially one "right" answer at every position (signature pinned, no
# comments allowed, exact output format requested). That maximizes the
# probability that two non-quantized endpoints produce byte-identical text,
# so any divergence is signal.

ROLLOUT_PANEL_ID = "rollout-v1"

ROLLOUT_PROMPTS: List[PromptItem] = [
    PromptItem(
        "py_merge_sort",
        _msgs(
            _SYS_IDE,
            "Write a clean Python implementation of merge sort using this exact "
            "signature:\n\n"
            "def merge_sort(arr: list[int]) -> list[int]:\n\n"
            "Include a helper `def merge(left: list[int], right: list[int]) -> list[int]:`. "
            "No docstrings, no comments, no markdown fences. Just the two functions, "
            "four-space indent, standard library only.",
        ),
    ),
    PromptItem(
        "py_bisect_left",
        _msgs(
            _SYS_IDE,
            "Reimplement Python's bisect.bisect_left from scratch with this signature:\n\n"
            "def bisect_left(a, x, lo=0, hi=None):\n\n"
            "Pure Python, standard library only, no comments, no docstring, no "
            "markdown fences. Just the function body.",
        ),
    ),
    PromptItem(
        "py_dijkstra",
        _msgs(
            _SYS_IDE,
            "Implement Dijkstra's shortest-path algorithm in Python using heapq. "
            "Signature:\n\n"
            "def dijkstra(graph: dict[int, list[tuple[int, int]]], start: int) -> dict[int, int]:\n\n"
            "Each edge in the adjacency list is (neighbor, weight). Return a dict "
            "mapping every reachable node to its minimum distance from `start`. "
            "No comments, no docstring, no markdown fences. Just the function.",
        ),
    ),
    PromptItem(
        "py_lru_cache",
        _msgs(
            _SYS_IDE,
            "Write a Python LRU cache class with this exact interface:\n\n"
            "class LRUCache:\n"
            "    def __init__(self, capacity: int) -> None: ...\n"
            "    def get(self, key: int) -> int: ...   # returns -1 if missing\n"
            "    def put(self, key: int, value: int) -> None: ...\n\n"
            "Use collections.OrderedDict. O(1) per operation. No docstrings, no "
            "comments, no markdown fences.",
        ),
    ),
    PromptItem(
        "py_quicksort",
        _msgs(
            _SYS_IDE,
            "Write Lomuto-partition quicksort in Python using this exact signature:\n\n"
            "def quicksort(arr: list[int], lo: int = 0, hi: int | None = None) -> None:\n\n"
            "In-place sort. Include the partition helper as `def _partition(arr, lo, hi) -> int`. "
            "No docstrings, no comments, no markdown fences. Just the two functions.",
        ),
    ),
    PromptItem(
        "py_trie",
        _msgs(
            _SYS_IDE,
            "Implement a Trie in Python supporting `insert(word: str) -> None`, "
            "`search(word: str) -> bool`, and `starts_with(prefix: str) -> bool`. "
            "Use this class signature:\n\n"
            "class Trie:\n"
            "    def __init__(self) -> None: ...\n\n"
            "Use a nested dict for children. No docstrings, no comments, no markdown fences.",
        ),
    ),
    PromptItem(
        "ts_linked_list",
        _msgs(
            _SYS_IDE,
            "Write a TypeScript singly linked list with this exact shape:\n\n"
            "export class LinkedList<T> {\n"
            "  append(value: T): void;\n"
            "  prepend(value: T): void;\n"
            "  remove(value: T): boolean;\n"
            "  toArray(): T[];\n"
            "  get length(): number;\n"
            "}\n\n"
            "Use a private Node helper class. Strict mode, no `any`, no comments, "
            "no markdown fences. Two-space indent.",
        ),
    ),
    PromptItem(
        "ts_debounce",
        _msgs(
            _SYS_IDE,
            "Write a TypeScript debounce utility with this exact signature:\n\n"
            "export function debounce<T extends (...args: any[]) => void>(\n"
            "  fn: T,\n"
            "  waitMs: number\n"
            "): (...args: Parameters<T>) => void;\n\n"
            "Trailing-edge only. Uses setTimeout/clearTimeout. No comments, no "
            "markdown fences, two-space indent.",
        ),
    ),
    PromptItem(
        "ts_event_emitter",
        _msgs(
            _SYS_IDE,
            "Write a TypeScript EventEmitter class with this shape:\n\n"
            "export class EventEmitter<E extends Record<string, unknown[]>> {\n"
            "  on<K extends keyof E>(event: K, handler: (...args: E[K]) => void): () => void;\n"
            "  off<K extends keyof E>(event: K, handler: (...args: E[K]) => void): void;\n"
            "  emit<K extends keyof E>(event: K, ...args: E[K]): void;\n"
            "}\n\n"
            "`on` returns an unsubscribe function. Strict mode, no `any` outside the "
            "shape above, no comments, no markdown fences, two-space indent.",
        ),
    ),
    PromptItem(
        "go_fnv1a",
        _msgs(
            _SYS_IDE,
            "Write the FNV-1a 64-bit hash in Go with this exact signature:\n\n"
            "func FNV1a64(data []byte) uint64\n\n"
            "Use the standard offset basis 14695981039346656037 and prime "
            "1099511628211. Package name `hashx`. No comments, no doc comment, "
            "no markdown fences. Tab indent.",
        ),
    ),
    PromptItem(
        "go_ring_buffer",
        _msgs(
            _SYS_IDE,
            "Write a fixed-capacity generic ring buffer in Go 1.21+:\n\n"
            "type Ring[T any] struct { /* ... */ }\n"
            "func NewRing[T any](capacity int) *Ring[T]\n"
            "func (r *Ring[T]) Push(v T)\n"
            "func (r *Ring[T]) Pop() (T, bool)\n"
            "func (r *Ring[T]) Len() int\n\n"
            "Push when full overwrites the oldest. Package name `ringbuf`. No "
            "comments, no doc comments, no markdown fences. Tab indent.",
        ),
    ),
    PromptItem(
        "rust_levenshtein",
        _msgs(
            _SYS_IDE,
            "Write the Levenshtein distance function in Rust with this exact signature:\n\n"
            "pub fn levenshtein(a: &str, b: &str) -> usize\n\n"
            "Use the classic two-row dynamic programming approach. No comments, "
            "no doc comments, no markdown fences. Four-space indent.",
        ),
    ),
    PromptItem(
        "sql_users_table",
        _msgs(
            _SYS_IDE,
            "Write the PostgreSQL DDL for a `users` table with these columns:\n\n"
            "  id            BIGSERIAL PRIMARY KEY\n"
            "  email         VARCHAR(255) UNIQUE NOT NULL\n"
            "  password_hash CHAR(60) NOT NULL\n"
            "  display_name  VARCHAR(80)\n"
            "  is_active     BOOLEAN NOT NULL DEFAULT TRUE\n"
            "  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()\n"
            "  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()\n\n"
            "Then add a partial index `users_active_email_idx` on email WHERE "
            "is_active. Just the SQL, no comments, no markdown fences, two-space indent.",
        ),
    ),
    PromptItem(
        "sql_orders_join",
        _msgs(
            _SYS_IDE,
            "Write a PostgreSQL query that returns, per customer, their total order "
            "count and the sum of `orders.total_cents` over the last 30 days. Tables: "
            "customers(id, email, created_at), orders(id, customer_id, total_cents, "
            "placed_at). Columns in this exact order: customer_id, email, order_count, "
            "total_cents. Sort by total_cents DESC, then customer_id ASC. Just the "
            "SQL, no markdown fences, no comments, two-space indent.",
        ),
    ),
    PromptItem(
        "json_tsconfig",
        _msgs(
            _SYS_IDE,
            "Output a strict tsconfig.json for a Node 22 + TypeScript 5.6 library. "
            "compilerOptions: target ES2022, module NodeNext, moduleResolution NodeNext, "
            "strict true, noUncheckedIndexedAccess true, exactOptionalPropertyTypes true, "
            "declaration true, declarationMap true, sourceMap true, rootDir ./src, "
            "outDir ./dist, esModuleInterop true, forceConsistentCasingInFileNames true. "
            "include [\"src\"], exclude [\"dist\", \"node_modules\", \"**/*.test.ts\"]. "
            "Two-space indent. Just the JSON, no markdown fences.",
        ),
    ),
    PromptItem(
        "json_eslint_flat",
        _msgs(
            _SYS_IDE,
            "Output a flat ESLint config (eslint.config.js) as a single ES module "
            "exporting an array. Targets TypeScript files (**/*.ts, **/*.tsx) using "
            "@typescript-eslint/parser and the @typescript-eslint plugin's "
            "recommended-type-checked rules. Browser + node globals. Two-space indent. "
            "Just the JS, no comments, no markdown fences.",
        ),
    ),
    PromptItem(
        "yaml_github_actions",
        _msgs(
            _SYS_IDE,
            "Output a GitHub Actions workflow at .github/workflows/ci.yml. Triggers: "
            "push to main, pull_request to main. One job `test` on ubuntu-latest with "
            "Node 22. Steps: checkout (actions/checkout@v4), setup-node "
            "(actions/setup-node@v4 with node-version 22 and cache npm), `npm ci`, "
            "`npm run lint`, `npm test -- --run`. Two-space indent. Just the YAML, "
            "no comments, no markdown fences.",
        ),
    ),
    PromptItem(
        "py_to_go_translate",
        _msgs(
            _SYS_IDE,
            "Translate this Python function to idiomatic Go in package `mathx`. "
            "Just the Go function, no comments, no doc comment, no markdown fences. "
            "Tab indent.\n\n"
            "def gcd(a: int, b: int) -> int:\n"
            "    while b:\n"
            "        a, b = b, a % b\n"
            "    return abs(a)",
        ),
    ),
    PromptItem(
        "py_to_ts_translate",
        _msgs(
            _SYS_IDE,
            "Translate this Python function to TypeScript. Export it as `flatten`. "
            "Use generic <T>. No comments, no markdown fences, two-space indent.\n\n"
            "def flatten(xs):\n"
            "    out = []\n"
            "    for x in xs:\n"
            "        if isinstance(x, list):\n"
            "            out.extend(flatten(x))\n"
            "        else:\n"
            "            out.append(x)\n"
            "    return out",
        ),
    ),
    PromptItem(
        "py_uuid_v4_regex",
        _msgs(
            _SYS_IDE,
            "Write a Python function that validates a canonical UUID v4 string with "
            "this exact signature:\n\n"
            "def is_uuid_v4(s: str) -> bool:\n\n"
            "Use re.fullmatch with a single compiled module-level pattern named "
            "`_UUID_V4_RE`. Accept lowercase hex only. No docstring, no comments, "
            "no markdown fences.",
        ),
    ),
]
assert len(ROLLOUT_PROMPTS) == 20


# ---------------------------------------------------------------------------
# Test 4 — Arithmetic stress (panel of 100)
# ---------------------------------------------------------------------------
#
# A mix of 4x4, 5x5, and 6x6 digit multiplications. Each item is wrapped in
# one of a few natural framings ("I'm writing a unit-test fixture / golden
# value / migration check"). The wrapping changes per item, but for any
# single item the prompt text is fixed across runs (identical params is the
# whole point of T=0 N-shot modal sampling).

_ARITH_FRAMINGS = (
    "I'm writing a unit-test fixture and need the exact value of {a} * {b}. "
    "Reply with the integer only — no commas, no scientific notation, no prose.",
    "Quick golden value for a regression test: what is {a} * {b}? "
    "Just the integer, no commas, no formatting.",
    "Sanity-checking a SQL migration that computes {a} * {b}. Give me the exact "
    "product as a plain integer, no commas, no thousands separators.",
    "I need a constant in a config file equal to {a} * {b}. Reply with only the "
    "integer — no commas, no scientific notation.",
    "Need to hard-code the value of {a} * {b} in a Go test. Reply with the integer "
    "only, no commas.",
)


def _build_arithmetic_panel(n: int = 100, seed: int = 20260425) -> list[PromptItem]:
    rng = random.Random(seed)
    items: list[PromptItem] = []
    # Roughly 1/3 each of 4x4, 5x5, 6x6 digit multiplications.
    splits = [(4, n // 3), (5, n // 3), (6, n - 2 * (n // 3))]
    idx = 0
    for digits, count in splits:
        lo = 10 ** (digits - 1)
        hi = 10 ** digits - 1
        for _ in range(count):
            a = rng.randint(lo, hi)
            b = rng.randint(lo, hi)
            framing = rng.choice(_ARITH_FRAMINGS)
            items.append(
                PromptItem(
                    name=f"mul{digits}x{digits}_{idx:03d}",
                    messages=_msgs(_SYS_IDE, framing.format(a=a, b=b)),
                    meta={"a": a, "b": b, "expected": a * b, "digits": digits},
                )
            )
            idx += 1
    rng.shuffle(items)
    return items


ARITHMETIC_PANEL_ID = "arithmetic-v1"
ARITHMETIC_PROMPTS: List[PromptItem] = _build_arithmetic_panel()
assert len(ARITHMETIC_PROMPTS) == 100


# ---------------------------------------------------------------------------
# Test 6 — Sampling entropy (panel of 10)
# ---------------------------------------------------------------------------
#
# Open-ended prompts where many first tokens are reasonable. Quantization
# tends to flatten logit distributions, so at T=1 the first-token entropy
# of a quantized endpoint is measurably higher than the reference. Prompts
# stay coder-flavored to fit the rest of the audit traffic.

ENTROPY_PANEL_ID = "entropy-v1"

ENTROPY_PROMPTS: List[PromptItem] = [
    PromptItem(
        "name_a_caching_lib",
        _msgs(
            _SYS_PAIR,
            "Suggest a single-word name for a new in-memory caching library. "
            "Just the name, no explanation.",
        ),
    ),
    PromptItem(
        "name_a_test_runner",
        _msgs(
            _SYS_PAIR,
            "Suggest a single-word name for a new JavaScript test runner. Just "
            "the name, no explanation.",
        ),
    ),
    PromptItem(
        "name_a_static_site_gen",
        _msgs(
            _SYS_PAIR,
            "Suggest a single-word name for a new static site generator written "
            "in Rust. Just the name, no explanation.",
        ),
    ),
    PromptItem(
        "name_a_orm",
        _msgs(
            _SYS_PAIR,
            "Suggest a single-word codename for a new Python ORM. Just the name, "
            "no explanation.",
        ),
    ),
    PromptItem(
        "fav_lang_for_cli",
        _msgs(
            _SYS_PAIR,
            "What language would you reach for first to write a small CLI tool? "
            "Answer with one word.",
        ),
    ),
    PromptItem(
        "first_thing_in_new_repo",
        _msgs(
            _SYS_PAIR,
            "What's the first file you'd add to a brand-new project repository? "
            "Answer with just the filename.",
        ),
    ),
    PromptItem(
        "favourite_text_editor",
        _msgs(
            _SYS_PAIR,
            "Pick one text editor you'd recommend to a new developer. One word.",
        ),
    ),
    PromptItem(
        "favourite_db",
        _msgs(
            _SYS_PAIR,
            "Pick one database you'd reach for in a new side project. One word.",
        ),
    ),
    PromptItem(
        "haiku_about_debugging",
        _msgs(
            _SYS_PAIR,
            "Write the first line of a haiku about debugging. Just the line.",
        ),
    ),
    PromptItem(
        "describe_monday_morning",
        _msgs(
            _SYS_PAIR,
            "Describe a Monday morning standup meeting in three words.",
        ),
    ),
]
assert len(ENTROPY_PROMPTS) == 10
