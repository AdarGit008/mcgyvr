from solution import driest_window

assert driest_window([4], 1) == 0, "a single day names index zero"
assert driest_window([3, 1, 4, 1, 5], 1) == 1, "width one finds the smallest reading, earliest on a tie"
assert driest_window([4, 2, 0, 3], 2) == 1, "the driest two-day stretch starts at index one"
assert driest_window([2, 2, 2, 2], 3) == 0, "an all-tie record keeps the earliest start"
assert driest_window([9, 1, 1, 9], 4) == 0, "width equal to the record names the whole record"
assert driest_window([0, 6, 0, 6, 0], 3) == 0, "a later equal stretch does not displace the earliest"


def rejects(*args):
    try:
        driest_window(*args)
    except ValueError:
        return True
    return False


assert rejects("wet", 2), "a rain argument that is not a list is rejected"
assert rejects([1, 2.5, 3], 2), "a fractional reading is rejected"
assert rejects([1, -2, 3], 2), "a negative reading is rejected"
assert rejects([1, 2, 3], 0), "a zero width is rejected"
assert rejects([1, 2, 3], 4), "a width larger than the record is rejected"
print("ok")
