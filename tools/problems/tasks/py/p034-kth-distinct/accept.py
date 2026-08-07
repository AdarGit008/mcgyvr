from solution import kth_distinct

assert kth_distinct([7, 3, 3, 9], 1) == 3, "rank one after collapsing"
assert kth_distinct([7, 3, 3, 9], 2) == 7, "rank two skips the duplicate"
assert kth_distinct([7, 3, 3, 9], 3) == 9, "top rank"
assert kth_distinct([5], 1) == 5, "single element"
assert kth_distinct([4, 4, 4, 4], 1) == 4, "all duplicates collapse to one"
assert kth_distinct([10, -2, 0, -2, 10, 6], 2) == 0, "unsorted with negatives"
assert kth_distinct([100, 20, 300], 3) == 300, "largest distinct value"


def rejects(*args):
    try:
        kth_distinct(*args)
    except ValueError:
        return True
    return False


assert rejects([7, 3, 3, 9], 4), "rank past distinct count is rejected"
assert rejects([1, 2], 0), "zero rank is rejected"
assert rejects([1, 2], 1.5), "fractional rank is rejected"
assert rejects([], 1), "empty input is rejected"
assert rejects([1, "b"], 1), "non-integer element is rejected"
print("ok")
