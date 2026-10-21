"""Procedurally generated multi-step problems for `test_reasoning_budget.py`.

Every problem has an exact integer answer computed here in Python, needs
several dependent steps (so a model that is allowed to think scores much
better than one that isn't), and is generated from a fixed seed so the panel
hash is stable. Templates are deliberately varied so no single shortcut
(memorized fact, closed form) solves the whole panel.

Bump REASONING_PANEL_ID when templates, the seed, or the count change.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from math import comb
from typing import Callable, List

from framework import PromptItem

REASONING_PANEL_ID = "reasoning-budget-v1"
_SEED = 1618033
_PER_TEMPLATE = 4

_SYS = (
    "You are a careful assistant. Work the problem out, then finish with a "
    "final line of the form `ANSWER: <integer>` and nothing after it."
)


def _inclusion_exclusion(rng: random.Random) -> tuple[str, int]:
    n = rng.randint(5_000, 50_000)
    a, b = rng.sample([3, 4, 6, 7, 9, 11, 13], 2)
    c = rng.choice([5, 8, 10, 17, 19])
    ans = sum(1 for k in range(1, n + 1) if (k % a == 0 or k % b == 0) and k % c != 0)
    return (f"How many integers from 1 to {n} inclusive are divisible by {a} or by {b}, "
            f"but not divisible by {c}?", ans)


def _digit_sum_power(rng: random.Random) -> tuple[str, int]:
    base = rng.choice([2, 3, 7])
    exp = rng.randint(40, 90)
    ans = sum(int(d) for d in str(base ** exp))
    return f"What is the sum of the decimal digits of {base}^{exp}?", ans


def _recurrence(rng: random.Random) -> tuple[str, int]:
    a0 = rng.randint(2, 9)
    p, q, m = rng.randint(2, 7), rng.randint(1, 9), rng.choice([97, 101, 211, 1009])
    n = rng.randint(25, 45)
    x = a0
    for _ in range(n):
        x = (p * x * x + q) % m
    return (f"Define a_0 = {a0} and a_(k+1) = ({p}·a_k² + {q}) mod {m}. What is a_{n}?", x)


def _grid_paths(rng: random.Random) -> tuple[str, int]:
    w, h = rng.randint(6, 9), rng.randint(6, 9)
    bx, by = rng.randint(2, w - 2), rng.randint(2, h - 2)
    total = comb(w + h, w)
    through = comb(bx + by, bx) * comb((w - bx) + (h - by), w - bx)
    return (f"On a grid, you walk from (0,0) to ({w},{h}) using only unit steps right (+x) or "
            f"up (+y). How many such paths avoid the point ({bx},{by})?", total - through)


def _weekday_count(rng: random.Random) -> tuple[str, int]:
    start = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
    days = rng.randint(200, 700)
    end = start + timedelta(days=days)
    wd = rng.randint(0, 6)
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    ans = sum(1 for i in range(days + 1) if (start + timedelta(days=i)).weekday() == wd)
    return (f"How many {names[wd]}s are there from {start.isoformat()} to {end.isoformat()}, "
            f"both dates inclusive?", ans)


def _change_making(rng: random.Random) -> tuple[str, int]:
    coins = sorted(rng.sample([1, 2, 3, 5, 7, 10, 12, 25], 4))
    if 1 not in coins:
        coins[0] = 1
    target = rng.randint(40, 90)
    ways = [1] + [0] * target
    for c in coins:
        for v in range(c, target + 1):
            ways[v] += ways[v - c]
    return (f"In how many distinct ways can you make {target} using unlimited coins of "
            f"denominations {', '.join(map(str, coins))}? Order does not matter.", ways[target])


_TEMPLATES: tuple[tuple[str, Callable[[random.Random], tuple[str, int]]], ...] = (
    ("incl_excl", _inclusion_exclusion),
    ("digit_sum", _digit_sum_power),
    ("recurrence", _recurrence),
    ("grid_paths", _grid_paths),
    ("weekdays", _weekday_count),
    ("coin_change", _change_making),
)


def _build() -> List[PromptItem]:
    rng = random.Random(_SEED)
    items: List[PromptItem] = []
    for name, fn in _TEMPLATES:
        for i in range(_PER_TEMPLATE):
            question, answer = fn(rng)
            items.append(PromptItem(
                f"{name}_{i}",
                ({"role": "system", "content": _SYS}, {"role": "user", "content": question}),
                {"expected": answer, "template": name},
            ))
    return items


REASONING_PROMPTS: List[PromptItem] = _build()
