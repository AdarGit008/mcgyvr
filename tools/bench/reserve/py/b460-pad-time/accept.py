from solution import pad_time

assert pad_time(9, 5) == "09:05", "both parts are padded"
assert pad_time(12, 30) == "12:30", "neither part needs padding"
assert pad_time(0, 0) == "00:00", "midnight"
assert pad_time(23, 59) == "23:59", "the last minute of the day"
assert pad_time(9, 30) == "09:30", "only the hour needs padding"
assert pad_time(12, 5) == "12:05", "only the minute needs padding"
print("ok")
