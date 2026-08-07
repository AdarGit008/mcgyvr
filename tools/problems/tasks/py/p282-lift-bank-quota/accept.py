from solution import assign_lift_calls

PAIR = [
    {"name": "A", "floor": 0, "quota": 3},
    {"name": "B", "floor": 5, "quota": 3},
]

assert assign_lift_calls(PAIR, [4, 1, 8], 9) == [
    "B",
    "A",
    "B",
], "nearest standing cage answers, and it then stands at the call"
assert assign_lift_calls(PAIR, [], 9) == [], "no calls, no names"
assert assign_lift_calls(
    [{"name": "Z", "floor": 2, "quota": 5}, {"name": "A", "floor": 4, "quota": 5}],
    [3],
    6,
) == ["A"], "equal nearness and equal load falls to the earlier name, not list order"
assert assign_lift_calls(
    [{"name": "A", "floor": 0, "quota": 5}, {"name": "B", "floor": 0, "quota": 5}],
    [0, 0, 0],
    4,
) == ["A", "B", "A"], "the lighter load wins before the name does"
assert assign_lift_calls(
    [{"name": "A", "floor": 0, "quota": 1}, {"name": "B", "floor": 9, "quota": 1}],
    [1, 2, 3],
    9,
) == ["A", "B", "-"], "a spent bank marks the call and moves nobody"
assert assign_lift_calls([{"name": "solo", "floor": 3, "quota": 4}], [7, 7, 0], 7) == [
    "solo",
    "solo",
    "solo",
], "one cage answers until its quota runs out"
assert assign_lift_calls(
    [
        {"name": "A", "floor": 0, "quota": 2},
        {"name": "B", "floor": 10, "quota": 2},
        {"name": "C", "floor": 5, "quota": 2},
    ],
    [6, 6, 6, 6, 6, 6],
    10,
) == ["C", "C", "B", "B", "A", "A"], "a longer run drains every quota in turn"


def rejects(cars, calls, top):
    try:
        assign_lift_calls(cars, calls, top)
    except ValueError:
        return True
    return False


assert rejects([], [1], 5), "empty bank"
assert rejects(
    [{"name": "A", "floor": 0, "quota": 1}, {"name": "A", "floor": 1, "quota": 1}],
    [1],
    5,
), "repeated name"
assert rejects([{"name": "-", "floor": 0, "quota": 1}], [1], 5), (
    "the mark cannot be a cage name"
)
assert rejects([{"name": "A", "floor": 6, "quota": 1}], [1], 5), (
    "standing above the top floor"
)
assert rejects([{"name": "A", "floor": 0, "quota": 0}], [1], 5), "quota below one"
assert rejects([{"name": "A", "floor": 0, "quota": 1}], [-1], 5), (
    "call below the ground floor"
)
assert rejects([{"name": "A", "floor": 0, "quota": 1}], [2.5], 5), "a fractional call"
assert rejects([{"name": "A", "floor": 0, "quota": 1}], [1], 0), (
    "a building with no upper floor"
)
print("ok")
