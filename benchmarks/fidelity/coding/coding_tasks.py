"""Executable coding tasks for `test_code_exec.py`.

Each task is a small, self-contained Python function spec with hidden
assert-based tests that lean on edge cases (empty input, boundaries,
ordering rules, error handling). Frontier models solve most of them most of
the time — the point is not to rank models but to detect a *drop* on the
plan relative to the official API for the same model, and edge-case-heavy
tasks are where degraded deployments slip first.

Tasks are written fresh for this repo (not HumanEval/MBPP) so they are not in
any training set verbatim. Bump CODE_PANEL_ID when any task or test changes.
"""

from __future__ import annotations

from typing import List

from framework import PromptItem

CODE_PANEL_ID = "code-exec-v1"

_SYS = (
    "You are an expert Python developer. Reply with a single ```python code "
    "block containing the complete implementation (imports included) and "
    "nothing else. Standard library only."
)

# (name, spec, tests). `tests` is Python source run after the solution.
_TASKS: list[tuple[str, str, str]] = [
    (
        "parse_duration",
        "Write `parse_duration(text: str) -> int` that converts strings like '1h30m', "
        "'45s', '2h5s', '3m' into total seconds. Units are h, m, s, each at most once and "
        "in that order; whitespace around the whole string is allowed. Raise ValueError for "
        "empty strings, unknown units, repeated or out-of-order units, or missing numbers.",
        """
assert parse_duration('1h30m') == 5400
assert parse_duration(' 45s ') == 45
assert parse_duration('2h5s') == 7205
assert parse_duration('0m') == 0
for bad in ['', 'h', '5x', '1m1h', '1h1h', '10', 'm5']:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
""",
    ),
    (
        "semver_compare",
        "Write `semver_compare(a: str, b: str) -> int` returning -1, 0 or 1 comparing two "
        "Semantic Versioning 2.0.0 strings, including pre-release precedence rules "
        "(numeric identifiers compare numerically, numeric < alphanumeric, a larger set of "
        "identifiers wins when all preceding are equal, release > pre-release). Build "
        "metadata after '+' is ignored.",
        """
order = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta', '1.0.0-beta.2',
         '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0', '1.0.1', '1.1.0', '2.0.0']
for i in range(len(order) - 1):
    assert semver_compare(order[i], order[i + 1]) == -1, (order[i], order[i + 1])
    assert semver_compare(order[i + 1], order[i]) == 1
assert semver_compare('1.0.0+build.1', '1.0.0+build.2') == 0
assert semver_compare('10.0.0', '9.0.0') == 1
""",
    ),
    (
        "merge_intervals",
        "Write `merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]` "
        "that merges overlapping or touching closed intervals (e.g. (1,3) and (3,5) merge) and "
        "returns them sorted. Input may be unsorted, empty, or contain intervals given as "
        "(end, start) which must be normalized first.",
        """
assert merge_intervals([]) == []
assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]
assert merge_intervals([(8, 10), (1, 4), (2, 6)]) == [(1, 6), (8, 10)]
assert merge_intervals([(5, 1)]) == [(1, 5)]
assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]
assert merge_intervals([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]
""",
    ),
    (
        "lru_cache",
        "Write a class `LRUCache` with `__init__(self, capacity: int)`, `get(self, key) -> int` "
        "(returns -1 if missing) and `put(self, key, value) -> None`. Both operations must be "
        "O(1). `get` marks the key as most recently used; `put` on an existing key updates it "
        "and marks it most recently used. Capacity 0 stores nothing.",
        """
c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(1, 10)
c.put(4, 4)
assert c.get(3) == -1 and c.get(1) == 10 and c.get(4) == 4
z = LRUCache(0)
z.put(1, 1)
assert z.get(1) == -1
""",
    ),
    (
        "roman_to_int",
        "Write `roman_to_int(s: str) -> int` for strict modern Roman numerals 1..3999. Raise "
        "ValueError for invalid numerals such as 'IIII', 'IC', 'VX', 'MMMM', '' or lowercase.",
        """
assert roman_to_int('MCMXCIV') == 1994
assert roman_to_int('III') == 3
assert roman_to_int('MMMCMXCIX') == 3999
assert roman_to_int('XLII') == 42
for bad in ['IIII', 'IC', 'VX', 'MMMM', '', 'iv', 'IIV', 'XM']:
    try:
        roman_to_int(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
""",
    ),
    (
        "topo_sort",
        "Write `topo_sort(deps: dict[str, list[str]]) -> list[str]` where deps maps a node to "
        "the nodes it depends on (which must come before it). Nodes that only appear as "
        "dependencies are included. Among valid orders return the lexicographically smallest "
        "one. Raise ValueError if there is a cycle.",
        """
assert topo_sort({}) == []
assert topo_sort({'b': ['a'], 'c': ['a']}) == ['a', 'b', 'c']
assert topo_sort({'app': ['lib', 'util'], 'lib': ['util']}) == ['util', 'lib', 'app']
assert topo_sort({'z': [], 'y': [], 'x': ['z']}) == ['y', 'z', 'x']
try:
    topo_sort({'a': ['b'], 'b': ['a']})
except ValueError:
    pass
else:
    raise AssertionError('cycle')
""",
    ),
    (
        "wildcard_match",
        "Write `wildcard_match(pattern: str, text: str) -> bool` where '?' matches exactly one "
        "character and '*' matches any sequence (including empty). The whole text must match. "
        "It must run in polynomial time for long inputs.",
        """
assert wildcard_match('*', '')
assert wildcard_match('a?c', 'abc')
assert not wildcard_match('a?c', 'ac')
assert wildcard_match('*.py', 'main.py')
assert not wildcard_match('*.py', 'main.pyc')
assert wildcard_match('a*b*c', 'aXXbYYc')
assert not wildcard_match('', 'a')
assert not wildcard_match('a' + '*a' * 30 + 'b', 'a' * 60)
""",
    ),
    (
        "flatten_dict",
        "Write `flatten(obj) -> dict[str, object]` that flattens nested dicts and lists into "
        "dot-separated keys, using list indices as keys (e.g. {'a': [{'b': 1}]} -> {'a.0.b': 1}). "
        "Empty dicts and empty lists are kept as leaf values. A non-container top-level value "
        "maps to the key ''.",
        """
assert flatten({'a': {'b': 1, 'c': [2, {'d': 3}]}}) == {'a.b': 1, 'a.c.0': 2, 'a.c.1.d': 3}
assert flatten({'x': {}, 'y': []}) == {'x': {}, 'y': []}
assert flatten(5) == {'': 5}
assert flatten({}) == {}
assert flatten([1, [2]]) == {'0': 1, '1.0': 2}
""",
    ),
    (
        "evaluate_expression",
        "Write `evaluate(expr: str) -> float` that evaluates arithmetic with + - * / and "
        "parentheses, unary minus, decimal numbers and arbitrary whitespace, using normal "
        "precedence and left associativity. Do not use eval/exec/ast. Raise ValueError on "
        "malformed input and ZeroDivisionError on division by zero.",
        """
assert evaluate('1 + 2 * 3') == 7
assert evaluate('(1 + 2) * 3') == 9
assert evaluate('8 / 4 / 2') == 1
assert evaluate('-3 - -2') == -1
assert abs(evaluate(' 2.5*(-(1+1)) ') + 5) < 1e-9
assert evaluate('10 - 4 - 3') == 3
for bad in ['1 +', '(1', '2 3', '']:
    try:
        evaluate(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
try:
    evaluate('1/(2-2)')
except ZeroDivisionError:
    pass
else:
    raise AssertionError('zero')
""",
    ),
    (
        "rle",
        "Write `compress(s: str) -> str` and `decompress(s: str) -> str` for run-length "
        "encoding of lowercase-letter strings: runs of length 1 are written as the bare letter, "
        "longer runs as the letter followed by the decimal count (which may be more than one "
        "digit). decompress must invert compress.",
        """
assert compress('aaabccdddd') == 'a3bc2d4'
assert compress('') == ''
assert compress('a' * 12 + 'b') == 'a12b'
assert decompress('a12b') == 'a' * 12 + 'b'
for s in ['', 'z', 'abc', 'aabbbcccc', 'q' * 105]:
    assert decompress(compress(s)) == s
""",
    ),
    (
        "word_wrap",
        "Write `wrap(text: str, width: int) -> list[str]` that greedily wraps words "
        "(split on any whitespace) into lines of at most `width` characters, joining words with "
        "single spaces. Words longer than `width` are split into chunks of exactly `width` "
        "characters (last chunk may be shorter), each starting a new line. Empty text returns [].",
        """
assert wrap('', 10) == []
assert wrap('the quick brown fox', 10) == ['the quick', 'brown fox']
assert wrap('a  b\\n c', 3) == ['a b', 'c']
assert wrap('abcdefghij xy', 4) == ['abcd', 'efgh', 'ij', 'xy']
assert wrap('hello', 5) == ['hello']
""",
    ),
    (
        "median_sorted",
        "Write `median_two_sorted(a: list[int], b: list[int]) -> float` returning the median of "
        "the combined elements of two sorted lists in O(log(min(m, n))) time. Raise ValueError "
        "if both are empty.",
        """
assert median_two_sorted([1, 3], [2]) == 2
assert median_two_sorted([1, 2], [3, 4]) == 2.5
assert median_two_sorted([], [5]) == 5
assert median_two_sorted([1, 1, 1], [1, 1]) == 1
assert median_two_sorted([-5, 3, 6, 12, 15], [-12, -10, -6, -3, 4, 10]) == 3
try:
    median_two_sorted([], [])
except ValueError:
    pass
else:
    raise AssertionError('empty')
""",
    ),
    (
        "shortest_path",
        "Write `shortest_path(edges: list[tuple[str, str, int]], start: str, goal: str) -> "
        "list[str] | None` for a directed graph with non-negative weights. Return the node list "
        "of a minimum-cost path; if several have equal cost, return the one with fewer edges, "
        "and among those the lexicographically smallest node list. Return None if unreachable; "
        "[start] if start == goal.",
        """
e = [('a', 'b', 1), ('b', 'd', 1), ('a', 'c', 1), ('c', 'd', 1), ('a', 'd', 3)]
assert shortest_path(e, 'a', 'd') == ['a', 'b', 'd']
assert shortest_path(e, 'a', 'a') == ['a']
assert shortest_path(e, 'd', 'a') is None
e2 = [('s', 'x', 2), ('s', 'y', 1), ('y', 'z', 1), ('z', 't', 0), ('x', 't', 0)]
assert shortest_path(e2, 's', 't') == ['s', 'x', 't']
assert shortest_path([('a', 'b', 0)], 'a', 'b') == ['a', 'b']
""",
    ),
    (
        "ip_in_cidr",
        "Write `ip_in_cidr(ip: str, cidr: str) -> bool` for IPv4 without using the ipaddress "
        "module. Raise ValueError for malformed addresses (wrong octet count, octets outside "
        "0-255, leading zeros like '01') or prefix lengths outside 0-32.",
        """
assert ip_in_cidr('10.0.0.3', '10.0.0.0/30')
assert not ip_in_cidr('10.0.0.4', '10.0.0.0/30')
assert ip_in_cidr('8.8.8.8', '0.0.0.0/0')
assert ip_in_cidr('192.168.1.1', '192.168.1.1/32')
assert not ip_in_cidr('192.168.1.2', '192.168.1.1/32')
for ip, cidr in [('1.2.3', '1.0.0.0/8'), ('1.2.3.256', '1.0.0.0/8'), ('1.2.3.4', '1.0.0.0/33'),
                 ('01.2.3.4', '1.0.0.0/8')]:
    try:
        ip_in_cidr(ip, cidr)
    except ValueError:
        pass
    else:
        raise AssertionError((ip, cidr))
""",
    ),
    (
        "business_days",
        "Write `add_business_days(start: str, n: int, holidays: set[str]) -> str` where dates are "
        "ISO 'YYYY-MM-DD'. Move forward n business days (Mon-Fri, excluding holidays) for n > 0, "
        "backward for n < 0; n == 0 returns start unchanged even if it is a weekend.",
        """
assert add_business_days('2026-10-16', 1, set()) == '2026-10-19'
assert add_business_days('2026-10-16', 0, set()) == '2026-10-16'
assert add_business_days('2026-10-17', 1, set()) == '2026-10-19'
assert add_business_days('2026-10-19', -1, set()) == '2026-10-16'
assert add_business_days('2026-12-23', 2, {'2026-12-24', '2026-12-25'}) == '2026-12-29'
assert add_business_days('2026-02-27', 1, set()) == '2026-03-02'
""",
    ),
    (
        "grid_paths_obstacles",
        "Write `count_paths(grid: list[str]) -> int` counting monotone paths (right or down "
        "moves only) from the top-left to the bottom-right cell of a grid of '.' (open) and "
        "'#' (blocked) characters, modulo 1_000_000_007. Return 0 if the start or end is "
        "blocked or the grid is empty.",
        """
assert count_paths(['...', '.#.', '...']) == 2
assert count_paths(['#']) == 0
assert count_paths(['.']) == 1
assert count_paths([]) == 0
assert count_paths(['..', '.#']) == 0
assert count_paths(['.' * 40] * 40) == 929264847
""",
    ),
]


def _messages(spec: str) -> tuple[dict[str, str], ...]:
    return ({"role": "system", "content": _SYS}, {"role": "user", "content": spec})


CODE_PROMPTS: List[PromptItem] = [
    PromptItem(name, _messages(spec), {"tests": tests.strip() + "\n"})
    for name, spec, tests in _TASKS
]
