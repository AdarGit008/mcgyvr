from solution import any_over, window_any

assert any_over([1, 5], 3) is True, "one reading stands above"
assert any_over([1, 2], 3) is False, "none stands above"
assert window_any([1, 5, 1], 2, 3) == [True, True], "the high reading is in both"
assert window_any([1, 1, 1], 2, 3) == [False, False], "no run holds one"
assert window_any([], 2, 3) == [], "no readings at all"
assert window_any([5, 1, 1], 2, 3) == [True, False], "only the first run"
print("ok")
