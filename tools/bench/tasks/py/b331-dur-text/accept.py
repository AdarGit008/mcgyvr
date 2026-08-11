from solution import dur_hours, dur_text

assert dur_hours(90) == 1, "an hour and a half holds one hour"
assert dur_hours(59) == 0, "under an hour holds none"
assert dur_text(90) == "1h30m", "both parts are written"
assert dur_text(60) == "1h", "a whole hour drops the minutes"
assert dur_text(30) == "30m", "under an hour drops the hours"
assert dur_text(0) == "0m", "nothing is written 0m"
assert dur_text(125) == "2h5m", "two hours and a little"
print("ok")
