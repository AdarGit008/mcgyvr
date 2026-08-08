from solution import capped_compositions

assert capped_compositions(7, 2, 1, 6) == 6, "two dice reach seven six ways"
assert capped_compositions(10, 3, 1, 6) == 27, "three parts, order counted"
assert capped_compositions(6, 4, 0, 3) == 44, "zeros allowed as parts"
assert capped_compositions(36, 8, 0, 9) == 4816030, "eight digits summing to 36"
assert capped_compositions(5, 1, 1, 6) == 1, "one part in range fits one way"
assert capped_compositions(9, 1, 1, 6) == 0, "one part cannot exceed hi"
assert capped_compositions(3, 2, 4, 6) == 0, "total below the floor fits nothing"
assert capped_compositions(0, 3, 0, 2) == 1, "all-zero sequence is the only fit"


def rejects(*args):
    try:
        capped_compositions(*args)
    except ValueError:
        return True
    return False


assert rejects(5, 0, 0, 3), "zero parts rejected"
assert rejects(5, 2, -1, 3), "negative bound rejected"
assert rejects(5, 2, 3, 2), "lo above hi rejected"
assert rejects(1.5, 2, 0, 3), "fractional total rejected"
assert rejects(5, 2, 0, "6"), "string bound rejected"
print("ok")
