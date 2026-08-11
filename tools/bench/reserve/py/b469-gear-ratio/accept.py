from solution import gear_ratio


def rejects(first, second):
    try:
        gear_ratio(first, second)
    except Exception:
        return True
    return False


assert gear_ratio(4, 6) == "2:3", "a shared amount of two"
assert gear_ratio(9, 3) == "3:1", "the second divides the first"
assert gear_ratio(5, 7) == "5:7", "nothing is shared"
assert gear_ratio(12, 12) == "1:1", "the two counts match"
assert gear_ratio(0, 4) == "0:1", "a first count of nothing"
assert gear_ratio(100, 75) == "4:3", "a larger pair"
assert rejects(3, 0), "a second count of nothing is rejected"
print("ok")
