from solution import time_add

assert time_add(9, 0, 60) == [10, 0], "an hour on"
assert time_add(9, 30, 45) == [10, 15], "past the hour"
assert time_add(23, 30, 60) == [0, 30], "round past midnight"
assert time_add(0, 0, 0) == [0, 0], "nothing added"
assert time_add(10, 0, 1440) == [10, 0], "a whole day comes back round"
assert time_add(12, 0, 1500) == [13, 0], "more than a day"
print("ok")
