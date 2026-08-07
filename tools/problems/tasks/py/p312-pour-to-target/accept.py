from solution import pour_to_target


def rejects(capacities, wanted):
    try:
        pour_to_target(capacities, wanted)
    except ValueError:
        return True
    return False


assert pour_to_target([5], 0) == [], "nothing to do when zero is wanted"
assert pour_to_target([5], 5) == ["fill A"], "one vessel, one fill"
assert pour_to_target([5], 3) is None, "a lone vessel cannot split itself"
assert pour_to_target([3, 5], 3) == ["fill A"], "fills come first"
assert pour_to_target([3, 5], 5) == ["fill B"], "second vessel filled"
assert pour_to_target([3, 5], 2) == [
    "fill B",
    "pour B A",
], "the remainder left behind after a pour"
assert pour_to_target([3, 5], 4) == [
    "fill B",
    "pour B A",
    "empty A",
    "pour B A",
    "fill B",
    "pour B A",
], "six actions for four litres"
assert pour_to_target([1, 2, 3], 3) == ["fill C"], "the third vessel is labelled C"
assert pour_to_target([2, 4], 3) is None, "even vessels never leave an odd amount"
assert pour_to_target([3, 5], 7) is None, "more than any vessel can hold"
assert rejects([], 1), "no vessels is rejected"
assert rejects([0, 5], 5), "a capacity of zero is rejected"
assert rejects([2.5, 5], 5), "a fractional capacity is rejected"
assert rejects([3, 5], -1), "a negative amount is rejected"
print("ok")
