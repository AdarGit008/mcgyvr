from solution import meter_charge

assert meter_charge(0, [[100, 2500]]) == 0, "no consumption bills nothing"
assert meter_charge(10, [[100, 2500]]) == 25, "a partial tier bills its exact cents"
assert meter_charge(3, [[100, 2500]]) == 8, "half a cent rounds up"
assert meter_charge(2, [[1, 1499], [1, 1499]]) == 2, "every tier rounds on its own"
assert meter_charge(150, [[100, 1000], [200, 500]]) == 125, (
    "consumption spills into the next tier"
)
assert meter_charge(3, [[2, 1000], [1, 2000]]) == 4, (
    "consumption may fill the ladder exactly"
)


def rejects(units, tiers):
    try:
        meter_charge(units, tiers)
    except Exception:
        return True
    return False


assert rejects(2.5, [[10, 100]]), "fractional units are rejected"
assert rejects(4, [[2, 100], [1, 100]]), "consumption past the ladder is rejected"
assert rejects(0, []), "an empty ladder is rejected"
assert rejects(1, [[0, 100]]), "a zero span is rejected"
assert rejects(1, [[5, -1]]), "a negative rate is rejected"
assert rejects(1, [[5, 10.5]]), "a fractional rate is rejected"
print("ok")
