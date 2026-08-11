from solution import pair_gap


def rejects(value):
    try:
        pair_gap(value)
    except Exception:
        return True
    return False


assert pair_gap([1, 5, 3, 4]) == [3, 4], "the closest pair after sorting"
assert pair_gap([10, 1]) == [1, 10], "two values are the pair"
assert pair_gap([1, 2, 3]) == [1, 2], "a tie goes to the earlier pair"
assert pair_gap([5, 5]) == [5, 5], "a repeated value has no gap"
assert pair_gap([-3, -1, 10]) == [-3, -1], "negatives sort first"
assert rejects([1]), "one value cannot pair"
assert rejects([]), "no values cannot pair"
print("ok")
