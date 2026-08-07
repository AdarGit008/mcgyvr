from solution import count_trim_sticks

assert count_trim_sticks(100, [40, 40, 30], 3) == {
    "sticks": 2,
    "tails": [14, 67],
}, "a call too long for the bench stick fetches a fresh one"

assert count_trim_sticks(100, [], 3) == {
    "sticks": 0,
    "tails": [],
}, "a run with no calls fetches nothing"

assert count_trim_sticks(10, [10], 2) == {
    "sticks": 1,
    "tails": [0],
}, "a call as long as the stick leaves it carrying nothing"

assert count_trim_sticks(12, [5, 5, 5], 0) == {
    "sticks": 2,
    "tails": [2, 7],
}, "a bladeless saw still runs the stick out"

assert count_trim_sticks(8, [8, 8], 5) == {
    "sticks": 2,
    "tails": [0, 0],
}, "two full-length calls take two sticks"

assert count_trim_sticks(20, [3, 3, 3], 1) == {
    "sticks": 1,
    "tails": [8],
}, "short calls all come off one stick"

assert count_trim_sticks(30, [30, 1], 0) == {
    "sticks": 2,
    "tails": [0, 29],
}, "a spent stick is set aside rather than kept for a shorter call"


def rejects(stick, calls, blade):
    try:
        count_trim_sticks(stick, calls, blade)
    except ValueError:
        return True
    return False


assert rejects(0, [1], 0), "a stick below one is rejected"
assert rejects(1.5, [1], 0), "a stick that is not whole is rejected"
assert rejects(10, "40", 0), "a calls argument that is not a list is rejected"
assert rejects(10, [0], 0), "a call below one is rejected"
assert rejects(10, [2.5], 0), "a call that is not whole is rejected"
assert rejects(20, [5, 21], 0), "a call longer than a fresh stick is rejected"
assert rejects(10, [1], -1), "a blade below nought is rejected"
assert rejects(10, [1], 0.5), "a blade that is not whole is rejected"
print("ok")
