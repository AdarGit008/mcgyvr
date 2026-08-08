from solution import expiry_cache

assert expiry_cache(
    2,
    [
        ["set", 0, "a", 1, 10],
        ["set", 1, "b", 2, 3],
        ["get", 2, "a"],
        ["get", 4, "b"],
        ["set", 5, "c", 3, 10],
        ["get", 5, "c"],
        ["get", 5, "a"],
    ],
) == [1, -1, 3, 1], "expiry hides an entry and a purge frees its slot"
assert expiry_cache(
    2,
    [
        ["set", 0, "a", 7, 100],
        ["set", 0, "b", 8, 50],
        ["set", 1, "c", 9, 100],
        ["get", 1, "b"],
        ["get", 1, "a"],
        ["get", 1, "c"],
    ],
) == [-1, 7, 9], "the live entry with the earliest expiry is evicted"
assert expiry_cache(
    2,
    [
        ["set", 0, "x", 1, 10],
        ["set", 0, "m", 2, 10],
        ["set", 1, "z", 3, 10],
        ["get", 1, "m"],
        ["get", 1, "x"],
        ["get", 1, "z"],
    ],
) == [-1, 1, 3], "an expiry tie evicts the smallest key"
assert expiry_cache(
    1,
    [
        ["set", 0, "a", 1, 5],
        ["set", 1, "a", 2, 5],
        ["get", 5, "a"],
        ["get", 6, "a"],
    ],
) == [2, -1], "a live overwrite extends the lifetime and death lands exactly at expiry"
assert expiry_cache(
    1,
    [
        ["set", 0, "a", 1, 2],
        ["set", 2, "b", 2, 5],
        ["get", 2, "a"],
        ["get", 3, "b"],
    ],
) == [-1, 2], "a dead entry gives way without touching the newcomer"


def rejects(*args):
    try:
        expiry_cache(*args)
    except ValueError:
        return True
    return False


assert rejects(0, []), "zero capacity is rejected"
assert rejects(2, [["set", 0, "a", 1, 0]]), "zero ttl is rejected"
assert rejects(
    2, [["set", 5, "a", 1, 5], ["get", 4, "a"]]
), "a backwards clock is rejected"
assert rejects(2, [["put", 0, "a", 1, 5]]), "an unknown operation is rejected"
print("ok")
