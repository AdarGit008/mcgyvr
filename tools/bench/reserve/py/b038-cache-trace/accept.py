from solution import trace_cache


def report(**overrides):
    base = {
        "hits": 0,
        "misses": 0,
        "dropped": 0,
        "evictions": [],
        "contents": [],
        "hot_key": None,
        "peak": 0,
    }
    base.update(overrides)
    return base


assert trace_cache(2, []) == report(), "an empty trace yields zeros"
assert trace_cache(2, [["get", "a"]]) == report(
    misses=1
), "a get of an absent key is a miss and stores nothing"
assert trace_cache(2, [["put", "a"], ["get", "a"]]) == report(
    hits=1, contents=["a"], hot_key="a", peak=1
), "a put then get is a hit"
assert trace_cache(2, [["put", "a"], ["put", "b"], ["put", "c"]]) == report(
    evictions=["a"], contents=["c", "b"], peak=2
), "overflow evicts the least recently used key"
assert trace_cache(
    2, [["put", "a"], ["put", "b"], ["get", "a"], ["put", "c"]]
) == report(
    hits=1, evictions=["b"], contents=["c", "a"], hot_key="a", peak=2
), "a get refreshes recency and saves its key from eviction"
assert trace_cache(
    2, [["put", "a"], ["put", "b"], ["put", "a"], ["put", "c"]]
) == report(
    evictions=["b"], contents=["c", "a"], peak=2
), "a repeated put refreshes rather than duplicates"
assert trace_cache(
    2, [["put", "a"], ["put", "b"], ["del", "a"], ["put", "c"]]
) == report(
    dropped=1, contents=["c", "b"], peak=2
), "a del frees a slot so the next put evicts nothing"
assert trace_cache(2, [["del", "x"]]) == report(), "a del of an absent key is a no-op"
assert trace_cache(1, [["put", "a"], ["put", "b"], ["get", "a"]]) == report(
    misses=1, evictions=["a"], contents=["b"], peak=1
), "an evicted key misses on its next get"
assert trace_cache(1, [["put", "a"], ["put", "b"], ["put", "c"]]) == report(
    evictions=["a", "b"], contents=["c"], peak=1
), "capacity one evicts on every new put"
assert trace_cache(
    3, [["put", "a"], ["put", "b"], ["put", "c"], ["get", "b"]]
) == report(
    hits=1, contents=["b", "c", "a"], hot_key="b", peak=3
), "contents come back most recently used first"
assert trace_cache(2, [["put", "a"], ["del", "a"], ["put", "a"]]) == report(
    dropped=1, contents=["a"], peak=1
), "a key may be stored again after a del"
assert trace_cache(
    2,
    [
        ["put", "u1"],
        ["get", "u1"],
        ["put", "u2"],
        ["get", "u3"],
        ["put", "u3"],
        ["get", "u1"],
        ["del", "u2"],
        ["put", "u4"],
        ["get", "u3"],
    ],
) == report(
    hits=2, misses=2, dropped=1, evictions=["u1"], contents=["u3", "u4"],
    hot_key="u1", peak=2,
), "a mixed trace: a hit tie goes to the alphabetically first key"
assert trace_cache(3, [["put", "a"], ["put", "b"], ["put", "c"]]) == report(
    contents=["c", "b", "a"], peak=3
), "filling to exactly capacity evicts nothing"
assert trace_cache(
    3, [["put", "a"], ["put", "b"], ["get", "b"], ["get", "b"], ["get", "a"]]
) == report(
    hits=3, contents=["a", "b"], hot_key="b", peak=2
), "the hottest key is the one with the most hits"


def rejects(capacity, requests):
    try:
        trace_cache(capacity, requests)
    except Exception:
        return True
    return False


assert rejects(0, []), "zero capacity is rejected"
assert rejects(2.5, []), "fractional capacity is rejected"
assert rejects(2, "x"), "non-list trace is rejected"
assert rejects(2, [["get"]]), "a one-item entry is rejected"
assert rejects(2, [["peek", "a"]]), "an unknown operation is rejected"
assert rejects(2, [["get", ""]]), "an empty key is rejected"
assert rejects(2, [["get", 7]]), "a non-string key is rejected"
print("ok")
