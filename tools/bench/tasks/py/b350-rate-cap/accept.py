from solution import rate_cap

assert rate_cap(1000, 10, 50) == 1050, "the cap bites"
assert rate_cap(1000, 10, 500) == 1100, "the cap is out of reach"
assert rate_cap(1000, 0, 50) == 1000, "no rate, no rise"
assert rate_cap(0, 10, 50) == 0, "nothing to raise"
assert rate_cap(100, 10, 10) == 110, "the rise lands exactly on the cap"
assert rate_cap(999, 10, 1000) == 1098, "the rise is rounded down"
print("ok")
