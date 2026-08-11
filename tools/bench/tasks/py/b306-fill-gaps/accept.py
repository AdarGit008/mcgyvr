from solution import is_gap, fill_gaps

assert is_gap(-1) is True, "minus one is missing"
assert is_gap(0) is False, "zero is a real reading"
assert fill_gaps([5, -1, 7]) == [5, 5, 7], "the earlier reading fills it"
assert fill_gaps([-1, 5]) == [-1, 5], "nothing came before"
assert fill_gaps([]) == [], "no readings at all"
assert fill_gaps([-1, 5, -1, 7]) == [
    -1,
    5,
    5,
    7,
], "a leading gap stays, a later one fills"
assert fill_gaps([3, 3]) == [3, 3], "nothing to fill"
print("ok")
