from solution import band_label, charge_percent

assert charge_percent(3400, 3000, 3800) == 50, "midpoint reads fifty"
assert charge_percent(3404, 3000, 3800) == 51, "half a percent rounds up"
assert charge_percent(3000, 3000, 3800) == 0, "the empty bound reads zero"
assert charge_percent(3800, 3000, 3800) == 100, "the full bound reads one hundred"
assert charge_percent(2500, 3000, 3800) == 0, "below empty clamps to zero"
assert charge_percent(4100, 3000, 3800) == 100, "above full clamps to one hundred"
assert band_label(14) == "low", "fourteen percent is low"
assert band_label(85) == "full", "eighty-five percent is full"


def rejects(*args):
    try:
        charge_percent(*args)
    except Exception:
        return True
    return False


assert rejects(3400.5, 3000, 3800), "fractional reading is rejected"
assert rejects(3400, 3800, 3800), "empty bound at full bound is rejected"
print("ok")
