from solution import time_gap

assert time_gap(9, 0, 10, 0) == 60, "an hour later"
assert time_gap(9, 30, 10, 0) == 30, "half an hour later"
assert time_gap(23, 0, 1, 0) == 120, "over midnight"
assert time_gap(10, 0, 10, 0) == 1440, "the same time is a whole day"
assert time_gap(0, 0, 23, 59) == 1439, "almost a whole day"
assert time_gap(9, 0, 9, 30) == 30, "within the same hour"
print("ok")
