from solution import group_totals

assert group_totals(
    [{"g": "a", "n": 1}, {"g": "a", "n": 2}, {"g": "b", "n": 5}], "g", "n"
) == [["b", 5], ["a", 3]], "amounts accumulate and totals sort descending"
assert group_totals(
    [{"g": "beta", "n": 4}, {"g": "alpha", "n": 4}, {"g": "gamma", "n": 4}], "g", "n"
) == [["alpha", 4], ["beta", 4], ["gamma", 4]], "equal totals fall back to label order"
assert group_totals(
    [{"g": "x", "n": 1}, {"g": "y", "n": 9}, {"g": "x", "n": 3}, {"g": "z", "n": 2}],
    "g",
    "n",
) == [["y", 9], ["x", 4], ["z", 2]], "three labels ranked by summed total"
assert group_totals(
    [{"g": "a", "n": 5}, {"g": "a", "n": -2}], "g", "n"
) == [["a", 3]], "negative amounts subtract"
assert group_totals(
    [{"team": "red", "pts": 2}, {"team": "red", "pts": 2}], "team", "pts"
) == [["red", 4]], "property names come from the arguments"
assert group_totals([], "g", "n") == [], "no rows, no totals"


def rejects(rows, key, field):
    try:
        group_totals(rows, key, field)
    except ValueError:
        return True
    return False


assert rejects([{"g": "a"}], "g", "n"), "missing amount rejected"
assert rejects([{"n": 1}], "g", "n"), "missing label rejected"
assert rejects([{"g": 7, "n": 1}], "g", "n"), "non-string label rejected"
assert rejects([{"g": "a", "n": 1.5}], "g", "n"), "fractional amount rejected"
assert rejects([{"g": "a", "n": "3"}], "g", "n"), "string amount rejected"
print("ok")
