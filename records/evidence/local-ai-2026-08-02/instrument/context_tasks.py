"""Fixed regression task set for the context-size experiment (issue #27).

20 real task contracts (see mvp/workers/task_contract_template.md), each with:
- contract:  the exact user-message text sent to the worker
- accept:    stdlib-only acceptance script, run as `python accept.py` in a
             temp dir next to the generated solution.py; exit 0 = accepted
- reference: known-good solution used by --selftest to validate the rig

The set is frozen for the experiment: do not edit tasks after results exist.
"""

TASKS = [
    # ---------------------------------------------------------- function_impl
    {
        "id": "t01",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t01 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def rle_encode(s: str) -> str
CONSTRAINTS:
  - Run-length encode: "aaabb" -> "a3b2", "ab" -> "a1b1", "" -> ""
  - Single characters still get a count of 1
  - Input contains only letters
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: decoding, digits in input, CLI, other functions.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [("aaabb", "a3b2"), ("", ""), ("a", "a1"), ("ab", "a1b1"),
         ("aabbbba", "a2b4a1"), ("zzzzz", "z5")]
for s, want in cases:
    got = solution.rle_encode(s)
    check(got == want, f"rle_encode({s!r}) = {got!r}, want {want!r}")
print("OK")
''',
        "reference": '''\
def rle_encode(s: str) -> str:
    """Run-length encode a string."""
    if not s:
        return ""
    parts = []
    prev, count = s[0], 1
    for ch in s[1:]:
        if ch == prev:
            count += 1
        else:
            parts.append(f"{prev}{count}")
            prev, count = ch, 1
    parts.append(f"{prev}{count}")
    return "".join(parts)
''',
    },
    {
        "id": "t02",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t02 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def merge_intervals(intervals: list[list[int]]) -> list[list[int]]
CONSTRAINTS:
  - Merge overlapping or touching intervals: [[1,3],[2,6],[8,10]] -> [[1,6],[8,10]]
  - Touching counts as overlapping: [[1,2],[2,3]] -> [[1,3]]
  - Input may be unsorted; output sorted by start
  - Must NOT mutate the input list or its elements
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: open/half-open intervals, floats, validation of malformed input.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [
    ([[1, 3], [2, 6], [8, 10]], [[1, 6], [8, 10]]),
    ([[1, 2], [2, 3]], [[1, 3]]),
    ([[5, 7], [1, 3]], [[1, 3], [5, 7]]),
    ([], []),
    ([[4, 4]], [[4, 4]]),
    ([[1, 10], [2, 3], [4, 5]], [[1, 10]]),
]
for arg, want in cases:
    got = solution.merge_intervals(arg)
    got = [list(iv) for iv in got]
    check(got == want, f"merge_intervals({arg}) = {got}, want {want}")

original = [[2, 6], [1, 3]]
snapshot = [list(iv) for iv in original]
solution.merge_intervals(original)
check(original == snapshot, f"input was mutated: {original} != {snapshot}")
print("OK")
''',
        "reference": '''\
def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    """Merge overlapping or touching closed intervals."""
    merged: list[list[int]] = []
    for start, end in sorted(iv[:] for iv in intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
''',
    },
    {
        "id": "t03",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t03 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def parse_semver(version: str) -> tuple[int, int, int, str | None]
CONSTRAINTS:
  - "1.2.3" -> (1, 2, 3, None); "1.2.3-beta.1" -> (1, 2, 3, "beta.1")
  - Prerelease part: after a "-", chars limited to [0-9A-Za-z.-]
  - Anything else raises ValueError: too few/many parts, non-numeric parts,
    empty string, build metadata ("1.2.3+meta" is invalid here)
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: full SemVer 2.0 spec, comparison/ordering, leading-zero rules.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

good = [
    ("1.2.3", (1, 2, 3, None)),
    ("0.0.1", (0, 0, 1, None)),
    ("10.20.30", (10, 20, 30, None)),
    ("1.2.3-beta.1", (1, 2, 3, "beta.1")),
    ("2.0.0-rc-1", (2, 0, 0, "rc-1")),
]
for arg, want in good:
    got = solution.parse_semver(arg)
    check(tuple(got) == want, f"parse_semver({arg!r}) = {got!r}, want {want!r}")

bad = ["1.2", "1.2.3.4", "x.2.3", "1.2.3+meta", "", "1..3", "1.2.three"]
for arg in bad:
    try:
        got = solution.parse_semver(arg)
    except ValueError:
        continue
    print(f"FAIL: parse_semver({arg!r}) should raise ValueError, got {got!r}")
    raise SystemExit(1)
print("OK")
''',
        "reference": '''\
import re

def parse_semver(version: str) -> tuple[int, int, int, str | None]:
    """Parse MAJOR.MINOR.PATCH[-prerelease] into a tuple."""
    m = re.fullmatch(r"(\\d+)\\.(\\d+)\\.(\\d+)(?:-([0-9A-Za-z.-]+))?", version)
    if not m:
        raise ValueError(f"invalid semver: {version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
''',
    },
    {
        "id": "t04",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t04 · project:local-ai · issue:#27 · tier:heavy
FILE(S): solution.py
INTERFACE: class LRUCache — __init__(self, capacity: int), get(self, key), put(self, key, value)
CONSTRAINTS:
  - get returns the stored value, or None if absent; get marks the key as
    recently used
  - put inserts/updates; when size would exceed capacity, evict the least
    recently used key first
  - capacity <= 0 raises ValueError in __init__
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: thread safety, TTL/expiry, __len__/__contains__, statistics.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

c = solution.LRUCache(2)
c.put("a", 1)
c.put("b", 2)
check(c.get("a") == 1, "get('a') after put should be 1")
c.put("c", 3)  # evicts "b" — "a" was refreshed by get
check(c.get("b") is None, "'b' should have been evicted (LRU)")
check(c.get("a") == 1, "'a' should survive")
check(c.get("c") == 3, "'c' should be present")
c.put("a", 99)  # update refreshes, no eviction
check(c.get("a") == 99, "update should overwrite value")
c.put("d", 4)  # evicts "c"
check(c.get("c") is None, "'c' should be evicted after 'a' was refreshed")
check(c.get("missing") is None, "missing key -> None")

try:
    solution.LRUCache(0)
    print("FAIL: LRUCache(0) should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
''',
        "reference": '''\
class LRUCache:
    """Least-recently-used cache with a fixed capacity."""

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        self.capacity = capacity
        self._data: dict = {}

    def get(self, key):
        """Return the value for key, refreshing its recency; None if absent."""
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def put(self, key, value) -> None:
        """Insert or update key, evicting the least recently used if full."""
        if key in self._data:
            self._data.pop(key)
        elif len(self._data) >= self.capacity:
            oldest = next(iter(self._data))
            del self._data[oldest]
        self._data[key] = value
''',
    },
    {
        "id": "t05",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t05 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def chunk_list(items: list, size: int) -> list[list]
CONSTRAINTS:
  - chunk_list([1,2,3,4,5], 2) -> [[1,2],[3,4],[5]]
  - Last chunk may be short; empty input -> []
  - size <= 0 raises ValueError
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: generators/iterators, padding, non-list sequences.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [
    (([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]),
    (([1, 2, 3, 4], 2), [[1, 2], [3, 4]]),
    (([], 3), []),
    (([1], 5), [[1]]),
    ((["a", "b", "c"], 1), [["a"], ["b"], ["c"]]),
]
for (items, size), want in cases:
    got = solution.chunk_list(items, size)
    got = [list(c) for c in got]
    check(got == want, f"chunk_list({items}, {size}) = {got}, want {want}")

for bad in (0, -2):
    try:
        solution.chunk_list([1, 2], bad)
        print(f"FAIL: chunk_list(_, {bad}) should raise ValueError")
        raise SystemExit(1)
    except ValueError:
        pass
print("OK")
''',
        "reference": '''\
def chunk_list(items: list, size: int) -> list[list]:
    """Split items into consecutive chunks of at most `size` elements."""
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    return [items[i:i + size] for i in range(0, len(items), size)]
''',
    },
    {
        "id": "t06",
        "type": "function_impl",
        "contract": '''\
CONTRACT ctx-t06 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def parse_csv_row(line: str) -> list[str]
CONSTRAINTS:
  - Split one CSV row on commas: 'a,b,c' -> ["a","b","c"]
  - Double-quoted fields may contain commas: '"a,b",c' -> ["a,b", "c"]
  - Doubled quotes inside a quoted field are a literal quote:
    '"say ""hi""",x' -> ['say "hi"', 'x']
  - Empty fields preserved: 'a,,b' -> ["a","","b"]; '' -> [""]
  - Do not import the csv module — implement the parsing yourself
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior and
  checks the csv module is not imported)
OUT OF SCOPE: multi-line rows, newline handling, other delimiters, writing.''',
        "accept": '''\
from pathlib import Path
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

src = Path("solution.py").read_text()
check("import csv" not in src.replace("  ", " "),
      "contract forbids importing the csv module")

cases = [
    ("a,b,c", ["a", "b", "c"]),
    ('"a,b",c', ["a,b", "c"]),
    ('"say ""hi""",x', ['say "hi"', "x"]),
    ("a,,b", ["a", "", "b"]),
    ("", [""]),
    ('"",a', ["", "a"]),
]
for line, want in cases:
    got = solution.parse_csv_row(line)
    check(got == want, f"parse_csv_row({line!r}) = {got!r}, want {want!r}")
print("OK")
''',
        "reference": '''\
def parse_csv_row(line: str) -> list[str]:
    """Parse one CSV row supporting double-quoted fields."""
    fields: list[str] = []
    field: list[str] = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    field.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                field.append(ch)
        elif ch == '"':
            in_quotes = True
        elif ch == ",":
            fields.append("".join(field))
            field = []
        else:
            field.append(ch)
        i += 1
    fields.append("".join(field))
    return fields
''',
    },
    {
        "id": "t07",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t07 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def flatten(nested: list) -> list
CONSTRAINTS:
  - Flatten arbitrarily nested lists: [1,[2,[3,4]],5] -> [1,2,3,4,5]
  - Only list instances are flattened — strings, tuples and every other
    value are atomic: ["ab",["cd"]] -> ["ab","cd"]; [(1,2),[3]] -> [(1,2),3]
  - Must handle at least 50 levels of nesting
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: flattening tuples/sets/generators, depth limits, laziness.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [
    ([1, [2, [3, 4]], 5], [1, 2, 3, 4, 5]),
    ([], []),
    ([[], [[]]], []),
    (["ab", ["cd"]], ["ab", "cd"]),
    ([(1, 2), [3]], [(1, 2), 3]),
    ([[[[1]]]], [1]),
]
for arg, want in cases:
    got = solution.flatten(arg)
    check(got == want, f"flatten({arg}) = {got}, want {want}")

deep = [0]
for _ in range(60):
    deep = [deep, 1]
got = solution.flatten(deep)
check(got == [0] + [1] * 60, f"60-level nesting failed: got {got[:5]}... len={len(got)}")
print("OK")
''',
        "reference": '''\
def flatten(nested: list) -> list:
    """Flatten arbitrarily nested lists; non-list values stay atomic."""
    flat: list = []
    stack = [iter(nested)]
    while stack:
        for item in stack[-1]:
            if isinstance(item, list):
                stack.append(iter(item))
                break
            flat.append(item)
        else:
            stack.pop()
    return flat
''',
    },
    {
        "id": "t08",
        "type": "function_impl",
        "contract": """\
CONTRACT ctx-t08 · project:local-ai · issue:#27 · tier:heavy
FILE(S): solution.py
INTERFACE: def topo_sort(n: int, edges: list[tuple[int, int]]) -> list[int]
CONSTRAINTS:
  - Nodes are 0..n-1; edge (a, b) means a must come before b
  - Return any valid topological order containing every node exactly once
  - Raise ValueError if the graph contains a cycle
  - n == 0 -> []
ACCEPTANCE: python accept.py (imports solution.py, verifies ordering
  constraints rather than one fixed answer)
OUT OF SCOPE: node validation, weighted edges, stable/lexicographic order.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

def verify(n, edges):
    order = solution.topo_sort(n, edges)
    check(sorted(order) == list(range(n)),
          f"topo_sort({n}, {edges}) = {order} is not a permutation of 0..{n-1}")
    pos = {v: i for i, v in enumerate(order)}
    for a, b in edges:
        check(pos[a] < pos[b], f"edge ({a},{b}) violated in {order}")

verify(4, [(0, 1), (0, 2), (1, 3), (2, 3)])
verify(3, [])
verify(0, [])
verify(6, [(5, 0), (5, 2), (4, 0), (4, 1), (2, 3), (3, 1)])
verify(2, [(1, 0)])

for n, edges in [(2, [(0, 1), (1, 0)]), (3, [(0, 1), (1, 2), (2, 0)]),
                 (1, [(0, 0)])]:
    try:
        got = solution.topo_sort(n, edges)
    except ValueError:
        continue
    print(f"FAIL: topo_sort({n}, {edges}) should raise ValueError (cycle), got {got}")
    raise SystemExit(1)
print("OK")
''',
        "reference": '''\
def topo_sort(n: int, edges: list[tuple[int, int]]) -> list[int]:
    """Kahn's algorithm; raises ValueError on a cycle."""
    indegree = [0] * n
    adjacent: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        adjacent[a].append(b)
        indegree[b] += 1
    queue = [v for v in range(n) if indegree[v] == 0]
    order: list[int] = []
    while queue:
        v = queue.pop()
        order.append(v)
        for w in adjacent[v]:
            indegree[w] -= 1
            if indegree[w] == 0:
                queue.append(w)
    if len(order) != n:
        raise ValueError("graph contains a cycle")
    return order
''',
    },
    # ---------------------------------------------------------------- bug_fix
    {
        "id": "t09",
        "type": "bug_fix",
        "contract": """\
CONTRACT ctx-t09 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def factorial(n: int) -> int
CONSTRAINTS:
  - Fix the bug in the code below; keep it recursive or make it iterative
  - factorial(0) == 1, factorial(5) == 120
  - Negative n raises ValueError
CODE:
  def factorial(n):
      if n == 0:
          return 0
      return n * factorial(n - 1)
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: floats, memoization, big-number optimizations.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

for n, want in [(0, 1), (1, 1), (5, 120), (10, 3628800)]:
    got = solution.factorial(n)
    check(got == want, f"factorial({n}) = {got}, want {want}")

try:
    solution.factorial(-1)
    print("FAIL: factorial(-1) should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
''',
        "reference": '''\
def factorial(n: int) -> int:
    """Return n! for non-negative n."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if n == 0:
        return 1
    return n * factorial(n - 1)
''',
    },
    {
        "id": "t10",
        "type": "bug_fix",
        "contract": """\
CONTRACT ctx-t10 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def binary_search(a: list[int], x: int) -> int
CONSTRAINTS:
  - Fix the bug in the code below (it can loop forever on some inputs)
  - Return the index of x in sorted list a, or -1 if absent
  - Keep it a binary search — no linear scans, no a.index()
CODE:
  def binary_search(a, x):
      lo, hi = 0, len(a)
      while lo < hi:
          mid = (lo + hi) // 2
          if a[mid] == x:
              return mid
          if a[mid] < x:
              lo = mid
          else:
              hi = mid
      return -1
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior; an
  infinite loop fails via harness timeout)
OUT OF SCOPE: duplicate handling guarantees, bisect module, non-int lists.""",
        "accept": '''\
from pathlib import Path
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

src = Path("solution.py").read_text().replace(" ", "")
check(".index(" not in src, "contract forbids a.index()")

a = [1, 3, 5, 7, 9, 11]
for x in a:
    got = solution.binary_search(a, x)
    check(got == a.index(x), f"binary_search({a}, {x}) = {got}, want {a.index(x)}")
for x in [0, 4, 12]:
    got = solution.binary_search(a, x)
    check(got == -1, f"binary_search({a}, {x}) = {got}, want -1")
check(solution.binary_search([], 5) == -1, "empty list -> -1")
check(solution.binary_search([2], 2) == 0, "single element found")
check(solution.binary_search([2], 3) == -1, "single element missing")
print("OK")
''',
        "reference": '''\
def binary_search(a: list[int], x: int) -> int:
    """Return the index of x in sorted a, or -1."""
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] == x:
            return mid
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return -1
''',
    },
    {
        "id": "t11",
        "type": "bug_fix",
        "contract": """\
CONTRACT ctx-t11 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def tag_item(name: str, tags: list[str] | None = None) -> list[str]
CONSTRAINTS:
  - Fix the bug: calls relying on the default must be independent —
    tag_item("a") -> ["a"], then tag_item("b") -> ["b"] (not ["a","b"])
  - When a list IS passed, append to it in place and return the same list
CODE:
  def tag_item(name, tags=[]):
      tags.append(name)
      return tags
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: deduplication, validation, tag normalization.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

check(solution.tag_item("a") == ["a"], "first default call should be ['a']")
check(solution.tag_item("b") == ["b"],
      "second default call should be ['b'] — default list must not accumulate")

mine = ["x"]
out = solution.tag_item("y", mine)
check(out is mine, "provided list must be returned (same object)")
check(mine == ["x", "y"], f"provided list must be appended in place, got {mine}")
print("OK")
''',
        "reference": '''\
def tag_item(name: str, tags: list[str] | None = None) -> list[str]:
    """Append name to tags, using a fresh list when none is given."""
    if tags is None:
        tags = []
    tags.append(name)
    return tags
''',
    },
    {
        "id": "t12",
        "type": "bug_fix",
        "contract": """\
CONTRACT ctx-t12 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def drop_small(counts: dict[str, int], threshold: int) -> dict[str, int]
CONSTRAINTS:
  - Fix the bug: the code below raises RuntimeError (dict changed size
    during iteration)
  - Must delete in place and return the SAME dict object — callers rely on
    identity, so rebuilding a new dict is wrong
CODE:
  def drop_small(counts, threshold):
      for key in counts:
          if counts[key] < threshold:
              del counts[key]
      return counts
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior and
  object identity)
OUT OF SCOPE: ordering guarantees, non-int values, copy variants.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

d = {"a": 1, "b": 5, "c": 2, "d": 9}
out = solution.drop_small(d, 3)
check(out is d, "must return the same dict object (in-place)")
check(d == {"b": 5, "d": 9}, f"drop_small result wrong: {d}")

d2 = {"x": 10}
out2 = solution.drop_small(d2, 3)
check(out2 is d2 and d2 == {"x": 10}, "nothing to drop should be a no-op")

d3 = {}
check(solution.drop_small(d3, 1) is d3, "empty dict should be a no-op")
print("OK")
''',
        "reference": '''\
def drop_small(counts: dict[str, int], threshold: int) -> dict[str, int]:
    """Delete entries below threshold in place and return the same dict."""
    for key in [k for k, v in counts.items() if v < threshold]:
        del counts[key]
    return counts
''',
    },
    {
        "id": "t13",
        "type": "bug_fix",
        "contract": """\
CONTRACT ctx-t13 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def reverse_words(sentence: str) -> str
CONSTRAINTS:
  - Fix the bug: "a b c" must become "c b a" (the code below drops a word)
  - Words are separated by single spaces; "" -> ""
CODE:
  def reverse_words(sentence):
      words = sentence.split(" ")
      out = []
      for i in range(len(words) - 1, 0, -1):
          out.append(words[i])
      return " ".join(out)
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: multiple/leading/trailing spaces, punctuation handling.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [("a b c", "c b a"), ("hello", "hello"), ("", ""),
         ("one two", "two one"), ("w x y z", "z y x w")]
for arg, want in cases:
    got = solution.reverse_words(arg)
    check(got == want, f"reverse_words({arg!r}) = {got!r}, want {want!r}")
print("OK")
''',
        "reference": '''\
def reverse_words(sentence: str) -> str:
    """Reverse the order of space-separated words."""
    return " ".join(sentence.split(" ")[::-1])
''',
    },
    # ---------------------------------------------------------------- refactor
    {
        "id": "t14",
        "type": "refactor",
        "contract": """\
CONTRACT ctx-t14 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def select_active(users: list[dict]) -> list[str]
CONSTRAINTS:
  - Refactor the code below to iterate directly (comprehension or for-in);
    behavior must be identical
  - Must NOT use range(len(...)) or index-based access into users
CODE:
  def select_active(users):
      result = []
      for i in range(len(users)):
          if users[i]["active"] and users[i]["age"] >= 18:
              result.append(users[i]["name"])
      return result
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior and
  checks range(len( is gone)
OUT OF SCOPE: sorting, deduplication, validation of user dicts.""",
        "accept": '''\
from pathlib import Path
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

src = Path("solution.py").read_text().replace(" ", "")
check("range(len(" not in src, "refactor must remove range(len(...)) indexing")

users = [
    {"name": "ann", "active": True, "age": 30},
    {"name": "bob", "active": False, "age": 40},
    {"name": "kid", "active": True, "age": 12},
    {"name": "cat", "active": True, "age": 18},
]
got = solution.select_active(users)
check(got == ["ann", "cat"], f"select_active = {got}, want ['ann', 'cat']")
check(solution.select_active([]) == [], "empty input -> []")
print("OK")
''',
        "reference": '''\
def select_active(users: list[dict]) -> list[str]:
    """Names of active adult users."""
    return [u["name"] for u in users if u["active"] and u["age"] >= 18]
''',
    },
    {
        "id": "t15",
        "type": "refactor",
        "contract": """\
CONTRACT ctx-t15 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def convert_temps(values: list[float], mode: str) -> list[int]
           def celsius_to_fahrenheit_rounded(values: list[float]) -> list[int]
           def celsius_to_kelvin_rounded(values: list[float]) -> list[int]
CONSTRAINTS:
  - Deduplicate the two functions below into convert_temps(values, mode)
    with mode "fahrenheit" or "kelvin"; any other mode raises ValueError
  - Keep BOTH original functions working as thin wrappers over convert_temps
CODE:
  def celsius_to_fahrenheit_rounded(values):
      out = []
      for v in values:
          out.append(round(v * 9 / 5 + 32))
      return out

  def celsius_to_kelvin_rounded(values):
      out = []
      for v in values:
          out.append(round(v + 273.15))
      return out
ACCEPTANCE: python accept.py (imports solution.py, asserts all three)
OUT OF SCOPE: other scales, unrounded variants, input validation.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

vals = [0.0, 100.0, -40.0, 36.6]
want_f = [32, 212, -40, 98]
want_k = [273, 373, 233, 310]

check(solution.convert_temps(vals, "fahrenheit") == want_f,
      f"convert_temps fahrenheit wrong: {solution.convert_temps(vals, 'fahrenheit')}")
check(solution.convert_temps(vals, "kelvin") == want_k,
      f"convert_temps kelvin wrong: {solution.convert_temps(vals, 'kelvin')}")
check(solution.celsius_to_fahrenheit_rounded(vals) == want_f,
      "celsius_to_fahrenheit_rounded wrapper broken")
check(solution.celsius_to_kelvin_rounded(vals) == want_k,
      "celsius_to_kelvin_rounded wrapper broken")
check(solution.convert_temps([], "kelvin") == [], "empty input -> []")

try:
    solution.convert_temps([1.0], "rankine")
    print("FAIL: unknown mode should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
''',
        "reference": '''\
def convert_temps(values: list[float], mode: str) -> list[int]:
    """Convert Celsius values to the target scale, rounded to ints."""
    if mode == "fahrenheit":
        return [round(v * 9 / 5 + 32) for v in values]
    if mode == "kelvin":
        return [round(v + 273.15) for v in values]
    raise ValueError(f"unknown mode: {mode!r}")


def celsius_to_fahrenheit_rounded(values: list[float]) -> list[int]:
    """Celsius -> Fahrenheit, rounded."""
    return convert_temps(values, "fahrenheit")


def celsius_to_kelvin_rounded(values: list[float]) -> list[int]:
    """Celsius -> Kelvin, rounded."""
    return convert_temps(values, "kelvin")
''',
    },
    {
        "id": "t16",
        "type": "refactor",
        "contract": """\
CONTRACT ctx-t16 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def fib(n: int) -> int
CONSTRAINTS:
  - The code below is exponential-time; replace it with an implementation
    that runs in linear time or better — fib(90) must return instantly
  - Same results: fib(0)=0, fib(1)=1, fib(n)=fib(n-1)+fib(n-2)
  - Negative n raises ValueError
CODE:
  def fib(n):
      if n < 2:
          return n
      return fib(n - 1) + fib(n - 2)
ACCEPTANCE: python accept.py (imports solution.py; fib(90) must complete
  within the harness timeout)
OUT OF SCOPE: closed-form/float approximations, caching decorators from
  outside the stdlib.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

for n, want in [(0, 0), (1, 1), (2, 1), (10, 55), (20, 6765)]:
    got = solution.fib(n)
    check(got == want, f"fib({n}) = {got}, want {want}")

got = solution.fib(90)
check(got == 2880067194370816120, f"fib(90) = {got}, want 2880067194370816120")

try:
    solution.fib(-1)
    print("FAIL: fib(-1) should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
''',
        "reference": '''\
def fib(n: int) -> int:
    """n-th Fibonacci number, iteratively."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
''',
    },
    # -------------------------------------------------------- type_annotation
    {
        "id": "t17",
        "type": "type_annotation",
        "contract": """\
CONTRACT ctx-t17 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def greet(name, greeting="Hello") / def total_length(strings)
CONSTRAINTS:
  - Add type annotations to both functions below; behavior unchanged
  - greet: both parameters str, returns str
  - total_length: parameter is list[str], returns int
CODE:
  def greet(name, greeting="Hello"):
      return greeting + ", " + name + "!"

  def total_length(strings):
      return sum(len(s) for s in strings)
ACCEPTANCE: python accept.py (checks typing.get_type_hints and behavior)
OUT OF SCOPE: TypeVar generics, runtime type checking, docstring changes.""",
        "accept": '''\
import typing
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

th = typing.get_type_hints(solution.greet)
check(th.get("name") is str, f"greet name annotation is {th.get('name')}, want str")
check(th.get("greeting") is str, f"greet greeting annotation is {th.get('greeting')}, want str")
check(th.get("return") is str, f"greet return annotation is {th.get('return')}, want str")

th2 = typing.get_type_hints(solution.total_length)
check(th2.get("strings") == list[str],
      f"total_length strings annotation is {th2.get('strings')}, want list[str]")
check(th2.get("return") is int, f"total_length return is {th2.get('return')}, want int")

check(solution.greet("Ada") == "Hello, Ada!", "greet behavior changed")
check(solution.greet("Ada", "Hi") == "Hi, Ada!", "greet custom greeting broken")
check(solution.total_length(["ab", "cde"]) == 5, "total_length behavior changed")
check(solution.total_length([]) == 0, "total_length([]) should be 0")
print("OK")
''',
        "reference": '''\
def greet(name: str, greeting: str = "Hello") -> str:
    """Format a greeting."""
    return greeting + ", " + name + "!"


def total_length(strings: list[str]) -> int:
    """Sum of the lengths of all strings."""
    return sum(len(s) for s in strings)
''',
    },
    {
        "id": "t18",
        "type": "type_annotation",
        "contract": """\
CONTRACT ctx-t18 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def find_user(users, user_id)
CONSTRAINTS:
  - Add type annotations; behavior unchanged
  - users: list[dict[str, int]]; user_id: int
  - Return type: dict[str, int] or None (use Optional[...] or the | None form)
CODE:
  def find_user(users, user_id):
      for user in users:
          if user["id"] == user_id:
              return user
      return None
ACCEPTANCE: python accept.py (checks typing.get_type_hints and behavior)
OUT OF SCOPE: TypedDict, dataclasses, changing the lookup logic.""",
        "accept": '''\
import typing
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

th = typing.get_type_hints(solution.find_user)
check(th.get("users") == list[dict[str, int]],
      f"users annotation is {th.get('users')}, want list[dict[str, int]]")
check(th.get("user_id") is int, f"user_id annotation is {th.get('user_id')}, want int")
ret = th.get("return")
want_ret = typing.Optional[dict[str, int]]
check(ret == want_ret, f"return annotation is {ret}, want {want_ret}")

users = [{"id": 1, "age": 30}, {"id": 2, "age": 40}]
check(solution.find_user(users, 2) == {"id": 2, "age": 40}, "lookup broken")
check(solution.find_user(users, 99) is None, "missing id should return None")
check(solution.find_user([], 1) is None, "empty list should return None")
print("OK")
''',
        "reference": '''\
def find_user(users: list[dict[str, int]], user_id: int) -> dict[str, int] | None:
    """Return the first user dict with a matching id, else None."""
    for user in users:
        if user["id"] == user_id:
            return user
    return None
''',
    },
    # -------------------------------------------------------------- edge_case
    {
        "id": "t19",
        "type": "edge_case",
        "contract": """\
CONTRACT ctx-t19 · project:local-ai · issue:#27 · tier:light
FILE(S): solution.py
INTERFACE: def safe_divide(a, b) -> float | None
CONSTRAINTS:
  - Return a / b as a float
  - b == 0 (int or float zero) -> return None, do not raise
  - Non-numeric a or b (str, None, list, ...) raises TypeError
  - bool is NOT accepted as numeric here — raise TypeError for bool
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: complex numbers, Decimal/Fraction, division precision tricks.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

check(solution.safe_divide(6, 3) == 2.0, "safe_divide(6,3) should be 2.0")
check(solution.safe_divide(7, 2) == 3.5, "safe_divide(7,2) should be 3.5")
check(solution.safe_divide(-9, 3.0) == -3.0, "float divisor should work")
check(solution.safe_divide(1, 0) is None, "b=0 -> None")
check(solution.safe_divide(1, 0.0) is None, "b=0.0 -> None")
check(solution.safe_divide(0, 5) == 0.0, "a=0 is fine")

for a, b in [("x", 1), (1, "x"), (None, 1), (1, None), ([1], 2),
             (True, 2), (4, False)]:
    try:
        got = solution.safe_divide(a, b)
    except TypeError:
        continue
    print(f"FAIL: safe_divide({a!r}, {b!r}) should raise TypeError, got {got!r}")
    raise SystemExit(1)
print("OK")
''',
        "reference": '''\
def safe_divide(a, b) -> float | None:
    """Divide a by b; None on zero divisor, TypeError on non-numbers."""
    for value in (a, b):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"expected int or float, got {type(value).__name__}")
    if b == 0:
        return None
    return a / b
''',
    },
    {
        "id": "t20",
        "type": "edge_case",
        "contract": """\
CONTRACT ctx-t20 · project:local-ai · issue:#27 · tier:medium
FILE(S): solution.py
INTERFACE: def read_config(text: str) -> dict[str, str]
CONSTRAINTS:
  - Parse KEY=VALUE lines; strip whitespace around both key and value
  - Skip blank lines and lines whose first non-space char is '#'
  - Split on the FIRST '=' only — values may contain '='
  - Empty value is allowed ("KEY=" -> ""); empty key raises ValueError
  - A non-comment line without '=' raises ValueError
  - Later duplicate keys override earlier ones
ACCEPTANCE: python accept.py (imports solution.py, asserts behavior)
OUT OF SCOPE: quoting, escapes, sections/INI features, type coercion.""",
        "accept": '''\
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

text = """
# comment
HOST = example.com
PORT=8080

  # indented comment
URL = https://x.io/?a=1&b=2
EMPTY=
HOST = override.com
"""
got = solution.read_config(text)
want = {"HOST": "override.com", "PORT": "8080",
        "URL": "https://x.io/?a=1&b=2", "EMPTY": ""}
check(got == want, f"read_config = {got}, want {want}")
check(solution.read_config("") == {}, "empty text -> {}")
check(solution.read_config("\\n\\n# only comments\\n") == {}, "comments only -> {}")

for bad in ["JUSTAWORD", "A=1\\nBROKEN LINE\\n", "=value", "  =x"]:
    try:
        got = solution.read_config(bad)
    except ValueError:
        continue
    print(f"FAIL: read_config({bad!r}) should raise ValueError, got {got!r}")
    raise SystemExit(1)
print("OK")
''',
        "reference": '''\
def read_config(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines into a dict."""
    config: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"malformed line: {line!r}")
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"empty key in line: {line!r}")
        config[key] = value.strip()
    return config
''',
    },
]
