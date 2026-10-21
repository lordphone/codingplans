"""Known-good solutions for every task in coding_tasks.py.

Not used by the audit itself. `benchmarks/selftest.py` runs each task's hidden
tests against these through the same sandbox the audit uses, so a typo in a
test (which would silently fail every endpoint equally) is caught offline.
"""

REFERENCE_SOLUTIONS: dict[str, str] = {
    "parse_duration": r'''
import re
def parse_duration(text):
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text.strip())
    if not text.strip() or not m or not any(m.groups()):
        raise ValueError(text)
    h, mi, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + s
''',
    "semver_compare": r'''
def semver_compare(a, b):
    def parse(v):
        v = v.split("+", 1)[0]
        core, _, pre = v.partition("-")
        return [int(x) for x in core.split(".")], (pre.split(".") if pre else [])
    def cmp(x, y):
        return (x > y) - (x < y)
    ca, pa = parse(a); cb, pb = parse(b)
    if ca != cb:
        return cmp(ca, cb)
    if not pa or not pb:
        return cmp(not pa, not pb)
    for x, y in zip(pa, pb):
        if x == y:
            continue
        xd, yd = x.isdigit(), y.isdigit()
        if xd and yd:
            return cmp(int(x), int(y))
        if xd != yd:
            return -1 if xd else 1
        return cmp(x, y)
    return cmp(len(pa), len(pb))
''',
    "merge_intervals": r'''
def merge_intervals(intervals):
    out = []
    for s, e in sorted((min(a, b), max(a, b)) for a, b in intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
''',
    "lru_cache": r'''
from collections import OrderedDict
class LRUCache:
    def __init__(self, capacity):
        self.cap = capacity; self.d = OrderedDict()
    def get(self, key):
        if key not in self.d:
            return -1
        self.d.move_to_end(key); return self.d[key]
    def put(self, key, value):
        if self.cap <= 0:
            return
        self.d[key] = value; self.d.move_to_end(key)
        if len(self.d) > self.cap:
            self.d.popitem(last=False)
''',
    "roman_to_int": r'''
import re
def roman_to_int(s):
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s) or not s:
        raise ValueError(s)
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for i, ch in enumerate(s):
        if i + 1 < len(s) and v[ch] < v[s[i + 1]]:
            total -= v[ch]
        else:
            total += v[ch]
    return total
''',
    "topo_sort": r'''
import heapq
def topo_sort(deps):
    nodes = set(deps) | {d for ds in deps.values() for d in ds}
    indeg = {n: 0 for n in nodes}; out = {n: [] for n in nodes}
    for n, ds in deps.items():
        for d in ds:
            out[d].append(n); indeg[n] += 1
    heap = [n for n in nodes if indeg[n] == 0]; heapq.heapify(heap); order = []
    while heap:
        n = heapq.heappop(heap); order.append(n)
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(heap, m)
    if len(order) != len(nodes):
        raise ValueError("cycle")
    return order
''',
    "wildcard_match": r'''
def wildcard_match(pattern, text):
    prev = [True] + [False] * len(text)
    for p in pattern:
        cur = [prev[0] and p == "*"] + [False] * len(text)
        for j, t in enumerate(text, 1):
            if p == "*":
                cur[j] = prev[j] or cur[j - 1]
            else:
                cur[j] = prev[j - 1] and (p == "?" or p == t)
        prev = cur
    return prev[-1]
''',
    "flatten_dict": r'''
def flatten(obj):
    out = {}
    def walk(v, key):
        if isinstance(v, dict) and v:
            for k, x in v.items():
                walk(x, f"{key}.{k}" if key else str(k))
        elif isinstance(v, list) and v:
            for i, x in enumerate(v):
                walk(x, f"{key}.{i}" if key else str(i))
        else:
            out[key] = v
    if isinstance(obj, (dict, list)) and not obj:
        return {}
    walk(obj, "")
    return out
''',
    "evaluate_expression": r'''
import re
def evaluate(expr):
    toks = re.findall(r"\d+\.?\d*|\.\d+|[-+*/()]|\S", expr)
    pos = 0
    def peek():
        return toks[pos] if pos < len(toks) else None
    def take():
        nonlocal pos
        if pos >= len(toks):
            raise ValueError("eof")
        pos += 1; return toks[pos - 1]
    def expr_():
        v = term()
        while peek() in ("+", "-"):
            v = v + term() if take() == "+" else v - term()
        return v
    def term():
        v = factor()
        while peek() in ("*", "/"):
            if take() == "*":
                v *= factor()
            else:
                d = factor()
                if d == 0:
                    raise ZeroDivisionError
                v /= d
        return v
    def factor():
        t = take()
        if t == "-":
            return -factor()
        if t == "(":
            v = expr_()
            if take() != ")":
                raise ValueError(")")
            return v
        try:
            return float(t)
        except ValueError:
            raise ValueError(t)
    v = expr_()
    if pos != len(toks):
        raise ValueError("trailing")
    return v
''',
    "rle": r'''
import re
def compress(s):
    return "".join(ch if len(m) == 1 else f"{ch}{len(m)}" for m, ch in re.findall(r"((.)\2*)", s))
def decompress(s):
    return "".join(ch * (int(n) if n else 1) for ch, n in re.findall(r"([a-z])(\d*)", s))
''',
    "word_wrap": r'''
def wrap(text, width):
    lines, cur = [], ""
    for w in text.split():
        while len(w) > width:
            if cur:
                lines.append(cur); cur = ""
            lines.append(w[:width]); w = w[width:]
        if not w:
            continue
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines
''',
    "median_sorted": r'''
def median_two_sorted(a, b):
    if len(a) > len(b):
        a, b = b, a
    m, n = len(a), len(b)
    if m + n == 0:
        raise ValueError("empty")
    lo, hi, half = 0, m, (m + n + 1) // 2
    while True:
        i = (lo + hi) // 2; j = half - i
        al = a[i - 1] if i > 0 else float("-inf"); ar = a[i] if i < m else float("inf")
        bl = b[j - 1] if j > 0 else float("-inf"); br = b[j] if j < n else float("inf")
        if al <= br and bl <= ar:
            if (m + n) % 2:
                return max(al, bl)
            return (max(al, bl) + min(ar, br)) / 2
        if al > br:
            hi = i - 1
        else:
            lo = i + 1
''',
    "shortest_path": r'''
import heapq
def shortest_path(edges, start, goal):
    adj = {}
    for u, v, w in edges:
        adj.setdefault(u, []).append((v, w))
    heap = [(0, 1, [start])]; done = set()
    while heap:
        cost, n, path = heapq.heappop(heap)
        node = path[-1]
        if node == goal:
            return path
        if node in done:
            continue
        done.add(node)
        for v, w in adj.get(node, []):
            if v not in done:
                heapq.heappush(heap, (cost + w, n + 1, path + [v]))
    return None
''',
    "ip_in_cidr": r'''
def ip_in_cidr(ip, cidr):
    def to_int(a):
        parts = a.split(".")
        if len(parts) != 4:
            raise ValueError(a)
        n = 0
        for p in parts:
            if not p.isdigit() or (len(p) > 1 and p[0] == "0") or int(p) > 255:
                raise ValueError(a)
            n = n * 256 + int(p)
        return n
    net, _, plen = cidr.partition("/")
    if not plen.isdigit() or not 0 <= int(plen) <= 32:
        raise ValueError(cidr)
    mask = (0xFFFFFFFF << (32 - int(plen))) & 0xFFFFFFFF
    return to_int(ip) & mask == to_int(net) & mask
''',
    "business_days": r'''
from datetime import date, timedelta
def add_business_days(start, n, holidays):
    d = date.fromisoformat(start); step = 1 if n > 0 else -1
    left = abs(n)
    while left:
        d += timedelta(days=step)
        if d.weekday() < 5 and d.isoformat() not in holidays:
            left -= 1
    return d.isoformat()
''',
    "grid_paths_obstacles": r'''
def count_paths(grid):
    if not grid or not grid[0] or grid[0][0] == "#" or grid[-1][-1] == "#":
        return 0
    w = len(grid[0]); row = [0] * w
    for r, line in enumerate(grid):
        for c, ch in enumerate(line):
            if ch == "#":
                row[c] = 0
            elif r == 0 and c == 0:
                row[c] = 1
            elif c > 0:
                row[c] = (row[c] + row[c - 1]) % 1_000_000_007
    return row[-1]
''',
}
