from solution import step_rate, rate_steps

assert step_rate(1000, 50, 10) == 150, "the fixed sum and a tenth"
assert step_rate(0, 50, 10) == 50, "nothing but the fixed sum"
assert step_rate(999, 0, 10) == 99, "the share is rounded down"
assert rate_steps([1000, 0], 50, 10) == [150, 50], "two amounts charged"
assert rate_steps([], 50, 10) == [], "no amounts at all"
assert step_rate(100, 0, 0) == 0, "no fixed sum and no share"
print("ok")
