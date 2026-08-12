from solution import unit_mix


def rejects(units, parts, per_unit):
    try:
        unit_mix(units, parts, per_unit)
    except Exception:
        return True
    return False


assert unit_mix(1, 7, 4) == [2, 3], "the parts carry into a unit"
assert unit_mix(0, 3, 4) == [0, 3], "nothing to carry"
assert unit_mix(2, 8, 4) == [4, 0], "the parts carry exactly"
assert unit_mix(0, 0, 4) == [0, 0], "nothing at all"
assert unit_mix(1, 4, 4) == [2, 0], "one unit's worth of parts"
assert rejects(1, 1, 0), "a unit of no parts is rejected"
print("ok")
