from solution import time_in

assert time_in(600, 540, 660) is True, "inside an ordinary window"
assert time_in(500, 540, 660) is False, "before it opens"
assert time_in(660, 540, 660) is False, "the closing minute is outside"
assert time_in(30, 1380, 60) is True, "after midnight in a window that wraps"
assert time_in(1400, 1380, 60) is True, "before midnight in the same window"
assert time_in(600, 1380, 60) is False, "the middle of the day is outside it"
print("ok")
