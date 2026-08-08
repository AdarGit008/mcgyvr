from solution import accrue_flat_interest

assert accrue_flat_interest(100000, 500, 365, 365) == 5000, "a full year at five percent"
assert accrue_flat_interest(100000, 600, 30, 360) == 500, "one month on a 360-day year"
assert accrue_flat_interest(5000000, 1250, 90, 360) == 156250, "a quarter at 12.5%"
assert accrue_flat_interest(180000, 10, 1, 360) == 1, "half a cent settles upward"
assert accrue_flat_interest(179999, 10, 1, 360) == 0, "just under half settles down"
assert accrue_flat_interest(180001, 10, 1, 360) == 1, "just over half settles up"
assert accrue_flat_interest(100000, 500, 0, 365) == 0, "no days, no earnings"
assert accrue_flat_interest(0, 500, 365, 365) == 0, "no principal, no earnings"
assert accrue_flat_interest(100000, 0, 365, 365) == 0, "no rate, no earnings"


def rejects(principal, rate, days, basis):
    try:
        accrue_flat_interest(principal, rate, days, basis)
    except ValueError:
        return True
    return False


assert rejects(-1, 500, 30, 360), "a negative principal is rejected"
assert rejects(100000, -5, 30, 360), "a negative rate is rejected"
assert rejects(100000, 500, -30, 360), "a negative day count is rejected"
assert rejects(100000, 500, 30, 366), "an unknown year basis is rejected"
assert rejects(100.5, 500, 30, 360), "a fractional principal is rejected"
assert rejects("100000", 500, 30, 360), "a non-number principal is rejected"
print("ok")
