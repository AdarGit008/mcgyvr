from solution import activity_float_table


def rejects(value):
    try:
        activity_float_table(value)
    except ValueError:
        return True
    return False


assert activity_float_table(
    [
        {"name": "a", "days": 3, "after": []},
        {"name": "b", "days": 2, "after": ["a"]},
        {"name": "c", "days": 4, "after": ["a"]},
        {"name": "d", "days": 1, "after": ["b", "c"]},
    ]
) == ["a 0 0 0", "b 3 5 2", "c 3 3 0", "d 7 7 0"], (
    "a fork and a join, with slack on the short arm"
)
assert activity_float_table([{"name": "solo", "days": 5, "after": []}]) == [
    "solo 0 0 0"
], "one activity alone"
assert activity_float_table(
    [{"name": "x", "days": 2, "after": []}, {"name": "y", "days": 5, "after": []}]
) == ["x 0 3 3", "y 0 0 0"], "two activities with nothing between them"
assert activity_float_table(
    [
        {"name": "zip", "days": 1, "after": []},
        {"name": "arc", "days": 2, "after": ["zip"]},
        {"name": "mid", "days": 3, "after": ["arc"]},
    ]
) == ["arc 1 1 0", "mid 3 3 0", "zip 0 0 0"], (
    "a chain reported in name order, not plan order"
)
assert activity_float_table(
    [
        {"name": "p", "days": 1, "after": []},
        {"name": "q", "days": 1, "after": ["p"]},
        {"name": "r", "days": 6, "after": ["p"]},
        {"name": "s", "days": 1, "after": ["q", "r"]},
    ]
) == ["p 0 0 0", "q 1 6 5", "r 1 1 0", "s 7 7 0"], (
    "a wide diamond gives one arm five days of slack"
)

assert rejects("a"), "not a list"
assert rejects([]), "an empty plan"
assert rejects(["a"]), "an entry that is not a mapping"
assert rejects([{"name": "", "days": 1, "after": []}]), "an empty name"
assert rejects(
    [{"name": "a", "days": 1, "after": []}, {"name": "a", "days": 2, "after": []}]
), "two entries share a name"
assert rejects([{"name": "a", "days": 0, "after": []}]), "zero days"
assert rejects([{"name": "a", "days": 1.5, "after": []}]), "a fractional day count"
assert rejects([{"name": "a", "days": 1, "after": "b"}]), (
    "an after list that is not a list"
)
assert rejects([{"name": "a", "days": 1, "after": ["ghost"]}]), (
    "an after entry naming nothing"
)
assert rejects([{"name": "a", "days": 1, "after": ["a"]}]), (
    "an activity waiting on itself"
)
assert rejects(
    [
        {"name": "a", "days": 1, "after": ["b"]},
        {"name": "b", "days": 1, "after": ["a"]},
    ]
), "a loop"
print("ok")
