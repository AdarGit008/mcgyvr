from solution import power_of


def rejects(base, power):
    try:
        power_of(base, power)
    except Exception:
        return True
    return False


assert power_of(2, 3) == 8, "two cubed"
assert power_of(5, 0) == 1, "a power of nothing gives one"
assert power_of(2, 1) == 2, "a power of one gives the base"
assert power_of(0, 3) == 0, "nothing to any power is nothing"
assert power_of(1, 10) == 1, "one to any power is one"
assert rejects(2, -1), "a negative power is rejected"
print("ok")
