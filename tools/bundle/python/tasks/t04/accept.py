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
