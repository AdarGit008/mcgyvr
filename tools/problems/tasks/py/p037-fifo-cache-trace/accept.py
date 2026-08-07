from solution import fifo_cache_trace

assert fifo_cache_trace(2, ["a", "b", "a", "c", "a"]) == [
    "miss",
    "miss",
    "hit",
    "miss",
    "miss",
], "a hit must not save `a` from FIFO eviction"
assert fifo_cache_trace(2, ["a", "b", "c", "b", "d", "c"]) == [
    "miss",
    "miss",
    "miss",
    "hit",
    "miss",
    "hit",
], "insertion order alone picks the victims"
assert fifo_cache_trace(1, ["a", "a", "b", "a"]) == [
    "miss",
    "hit",
    "miss",
    "miss",
], "capacity one keeps only the newest insertion"
assert fifo_cache_trace(3, ["a", "b", "c", "a", "b", "c"]) == [
    "miss",
    "miss",
    "miss",
    "hit",
    "hit",
    "hit",
], "no eviction below capacity"
assert fifo_cache_trace(2, []) == [], "empty log gives an empty trace"


def rejects(*args):
    try:
        fifo_cache_trace(*args)
    except ValueError:
        return True
    return False


assert rejects(0, ["a"]), "zero capacity is rejected"
assert rejects(2.5, ["a"]), "fractional capacity is rejected"
print("ok")
