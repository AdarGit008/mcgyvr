from solution import tier_cost


def rejects(units, allowance, first_rate, later_rate):
    try:
        tier_cost(units, allowance, first_rate, later_rate)
    except Exception:
        return True
    return False


assert tier_cost(5, 10, 2, 5) == 10, "inside the allowance"
assert tier_cost(10, 10, 2, 5) == 20, "exactly on the allowance"
assert tier_cost(12, 10, 2, 5) == 30, "only the excess costs more"
assert tier_cost(0, 10, 2, 5) == 0, "no units, no cost"
assert tier_cost(3, 0, 2, 5) == 15, "no allowance at all"
assert rejects(-1, 10, 2, 5), "negative units are rejected"
print("ok")
