from solution import digit_count

assert digit_count(0) == 1, "nothing takes one digit"
assert digit_count(5) == 1, "a single digit"
assert digit_count(42) == 2, "two digits"
assert digit_count(1000) == 4, "four digits"
assert digit_count(-37) == 2, "the minus sign is not counted"
assert digit_count(999999) == 6, "six digits"
print("ok")
