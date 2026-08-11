from solution import hour_rate, week_pay

assert hour_rate(10) == 10, "an hour is worth the rate"
assert week_pay(40, 10) == 400, "exactly the normal week"
assert week_pay(42, 10) == 430, "only the extra hours are dearer"
assert week_pay(0, 10) == 0, "no hours, no pay"
assert week_pay(41, 10) == 415, "one hour of overtime"
assert week_pay(10, 5) == 50, "a short week"
print("ok")
