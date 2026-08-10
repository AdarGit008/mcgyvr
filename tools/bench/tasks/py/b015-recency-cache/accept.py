from solution import cache_read, cache_write, new_cache

assert new_cache(2) == {"limit": 2, "keys": [], "store": {}}, "fresh cache"
cache = new_cache(2)
assert cache_write(cache, "a", 1) == [], "a write with room spills nothing"
cache_write(cache, "b", 2)
assert cache == {
    "limit": 2,
    "keys": ["a", "b"],
    "store": {"a": 1, "b": 2},
}, "state after two writes"
assert cache_write(cache, "c", 3) == ["a"], "a full write spills the oldest"
assert cache == {
    "limit": 2,
    "keys": ["b", "c"],
    "store": {"b": 2, "c": 3},
}, "the spilled key is gone from keys and store"
assert cache_write(cache, "b", 9) == [], "rewriting a held key spills nothing"
assert cache == {
    "limit": 2,
    "keys": ["c", "b"],
    "store": {"c": 3, "b": 9},
}, "a rewrite refreshes recency"
assert cache_write(cache, "d", 4) == ["c"], "the refreshed key survives the spill"
other = new_cache(2)
cache_write(other, "x", 7)
cache_write(other, "y", 8)
assert cache_read(other, "x") == 7, "read returns the held value"
assert cache_write(other, "z", 9) == ["y"], "reading x refreshed it, so y spills"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(cache_read, other, "q"), "reading a missing key is rejected"
assert rejects(new_cache, 0), "zero limit is rejected"
assert rejects(new_cache, 2.5), "fractional limit is rejected"
assert rejects(cache_write, other, 42, 1), "non-string key is rejected"
print("ok")
