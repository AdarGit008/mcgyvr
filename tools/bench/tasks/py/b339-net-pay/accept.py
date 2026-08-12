from solution import net_pay

assert net_pay(1000, 10, 50) == 850, "the rate comes off first"
assert net_pay(1000, 0, 50) == 950, "no rate, just the fee"
assert net_pay(100, 10, 0) == 90, "no fee, just the rate"
assert net_pay(100, 50, 100) == 0, "pay never falls below zero"
assert net_pay(0, 10, 0) == 0, "nothing earned, nothing paid"
assert net_pay(999, 10, 0) == 900, "the rate is rounded down"
print("ok")
