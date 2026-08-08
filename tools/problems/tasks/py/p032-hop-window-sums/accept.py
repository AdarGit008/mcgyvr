from solution import hop_window_sums

assert hop_window_sums([1, 2, 3, 4, 5], 3, 2) == [6, 12], "overlapping hop"
assert hop_window_sums([1, 2, 3, 4], 2, 2) == [3, 7], "tumbling windows"
assert hop_window_sums([1, 2, 3], 1, 1) == [1, 2, 3], "unit windows"
assert hop_window_sums([5, 5, 5], 3, 5) == [15], "single full window"
assert hop_window_sums([2, 4, 6, 8], 2, 3) == [6], "partial tail discarded"
assert hop_window_sums([], 2, 1) == [], "empty input"
assert hop_window_sums([1, 2], 3, 1) == [], "window larger than list"


def rejects(*args):
    try:
        hop_window_sums(*args)
    except ValueError:
        return True
    return False


assert rejects([1, 2], 0, 1), "zero size is rejected"
assert rejects([1, 2], 2, 0), "zero hop is rejected"
assert rejects([1, 2], 1.5, 1), "fractional size is rejected"
assert rejects("12", 1, 1), "non-list input is rejected"
assert rejects([1, "x"], 1, 1), "non-integer element is rejected"
print("ok")
