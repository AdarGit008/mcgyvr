from solution import mean_window

assert mean_window([1, 2, 3], 2) == [1, 2], "two windows, rounded down"
assert mean_window([2, 4, 6], 3) == [4], "one window over everything"
assert mean_window([1, 2], 5) == [], "the window does not fit"
assert mean_window([], 2) == [], "no readings at all"
assert mean_window([5, 5, 5], 1) == [5, 5, 5], "a window of one"
assert mean_window([1, 2, 3, 4], 2) == [1, 2, 3], "three windows"
print("ok")
