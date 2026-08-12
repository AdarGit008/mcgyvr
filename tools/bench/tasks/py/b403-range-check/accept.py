from solution import range_check


def rejects(readings, low, high):
    try:
        range_check(readings, low, high)
    except Exception:
        return True
    return False


assert range_check([1, 2], 1, 3) is True, "everything is inside"
assert range_check([0, 2], 1, 3) is False, "one reading falls short"
assert range_check([4], 1, 3) is False, "one reading overshoots"
assert range_check([], 1, 3) is True, "no readings fall outside anything"
assert range_check([1, 3], 1, 3) is True, "the bounds are included"
assert rejects([], 5, 1), "an upside-down range is rejected"
print("ok")
