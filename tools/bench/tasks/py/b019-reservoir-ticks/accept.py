from solution import run_reservoir

assert run_reservoir(10, 4, []) == {
    "level": 4,
    "spilled": 0,
    "shortfall": 0,
    "served": 0,
}, "no ticks leaves the starting level"
assert run_reservoir(10, 2, [[5, 0]]) == {
    "level": 7,
    "spilled": 0,
    "shortfall": 0,
    "served": 0,
}, "inflow within capacity just raises the level"
assert run_reservoir(10, 8, [[5, 0]]) == {
    "level": 10,
    "spilled": 3,
    "shortfall": 0,
    "served": 0,
}, "inflow past the brim spills the excess"
assert run_reservoir(10, 8, [[0, 5]]) == {
    "level": 3,
    "spilled": 0,
    "shortfall": 0,
    "served": 5,
}, "a covered demand is served in full"
assert run_reservoir(10, 3, [[0, 7]]) == {
    "level": 0,
    "spilled": 0,
    "shortfall": 4,
    "served": 3,
}, "an uncovered demand splits into served and shortfall"
assert run_reservoir(10, 9, [[4, 6]]) == {
    "level": 4,
    "spilled": 3,
    "shortfall": 0,
    "served": 6,
}, "inflow settles before the same tick's demand draws"
assert run_reservoir(10, 5, [[5, 0]]) == {
    "level": 10,
    "spilled": 0,
    "shortfall": 0,
    "served": 0,
}, "filling exactly to the brim spills nothing"
assert run_reservoir(10, 5, [[0, 5]]) == {
    "level": 0,
    "spilled": 0,
    "shortfall": 0,
    "served": 5,
}, "draining exactly to empty leaves no shortfall"
assert run_reservoir(8, 0, [[10, 2], [0, 8], [3, 1]]) == {
    "level": 2,
    "spilled": 2,
    "shortfall": 2,
    "served": 9,
}, "spill and shortfall accumulate across ticks"
assert run_reservoir(5, 5, [[0, 0]]) == {
    "level": 5,
    "spilled": 0,
    "shortfall": 0,
    "served": 0,
}, "a zero-zero tick changes nothing"


def rejects(capacity, start, ticks):
    try:
        run_reservoir(capacity, start, ticks)
    except Exception:
        return True
    return False


assert rejects(0, 0, []), "zero capacity is rejected"
assert rejects(5, 6, []), "start above capacity"
assert rejects(10, 5, [[1]]), "a one-item tick"
assert rejects(10, 5, [[-1, 0]]), "negative inflow"
assert rejects(10, 5, [[0, 1.5]]), "fractional demand"
print("ok")
