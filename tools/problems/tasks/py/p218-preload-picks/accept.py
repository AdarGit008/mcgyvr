from solution import preload_picks


def entry(key, size, hits):
    return {"key": key, "size": size, "hits": hits}


def rejects(entries, room):
    try:
        preload_picks(entries, room)
    except ValueError:
        return True
    return False


assert preload_picks([], 10) == [], "no candidates, nothing taken"
assert preload_picks([entry("a", 4, 2)], 10) == ["a"], "a candidate that fits is taken"
assert preload_picks([entry("a", 40, 2)], 10) == [], "a candidate too large is skipped"
assert preload_picks([entry("a", 1, 2)], 0) == [], "no room, nothing taken"
assert preload_picks(
    [entry("a", 1, 1), entry("b", 1, 5), entry("c", 1, 3)], 3
) == ["b", "c", "a"], "the line runs from most hits to fewest"
assert preload_picks([entry("a", 9, 5), entry("b", 2, 5)], 20) == [
    "b",
    "a",
], "equal hits favour the smaller size"
assert preload_picks([entry("zed", 2, 5), entry("abe", 2, 5)], 10) == [
    "abe",
    "zed",
], "equal hits and size favour the earlier key"
assert preload_picks([entry("big", 6, 9), entry("small", 5, 1)], 5) == [
    "small"
], "the line carries on past a candidate that will not fit"
assert preload_picks(
    [entry("a", 4, 9), entry("b", 3, 8), entry("c", 2, 7)], 6
) == ["a", "c"], "a later candidate takes the room the middle one could not"
assert preload_picks([entry("a", 5, 1), entry("b", 5, 2)], 10) == [
    "b",
    "a",
], "the room runs out exactly"

assert rejects("abc", 5), "a candidate list that is not a list is rejected"
assert rejects([], -1), "a negative room is rejected"
assert rejects([], 2.5), "a room that is not whole is rejected"
assert rejects([["a", 1, 1]], 5), "a candidate that is not a mapping is rejected"
assert rejects([{"size": 1, "hits": 1}], 5), "a missing key is rejected"
assert rejects([entry("", 1, 1)], 5), "an empty key is rejected"
assert rejects([entry("a", 1, 1), entry("a", 2, 2)], 5), "a repeated key is rejected"
assert rejects([entry("a", 0, 1)], 5), "a size of zero is rejected"
assert rejects([entry("a", 1, -1)], 5), "negative hits are rejected"

print("ok")
