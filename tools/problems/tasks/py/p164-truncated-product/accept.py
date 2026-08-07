from solution import truncated_product

assert truncated_product([1, 2], [1, 3], 5) == [1, 5, 6], "plain product"
assert truncated_product([3], [4], 0) == [12], "two constants"
assert truncated_product([2, -3, 1], [1, 1], 10) == [2, -1, -2, 1], "cap above degree"
assert truncated_product([1, -1], [1, 1, 1, 1], 4) == [
    1,
    0,
    0,
    0,
    -1,
], "interior zeros survive"
assert truncated_product([1, -1], [1, 1, 1, 1], 3) == [1], "cutting the top term"
assert truncated_product([1, -1], [1, 1], 1) == [1], "cut to a constant"
assert truncated_product([0, 1], [0, 1], 2) == [0, 0, 1], "shifted squares"
assert truncated_product([0, 1], [0, 1], 1) == [], "cut away to nothing"
assert truncated_product([], [1, 2], 3) == [], "zero times anything"
assert truncated_product([1, 1], [1, 1], 0) == [1], "cap zero keeps the constant"


def rejects(left, right, cap):
    try:
        truncated_product(left, right, cap)
    except ValueError:
        return True
    return False


assert rejects([1, 0], [1], 2), "trailing zero rejected"
assert rejects([1], [0], 2), "bare zero rejected"
assert rejects([1, 1.5], [1], 2), "fraction rejected"
assert rejects("x", [1], 2), "non-list rejected"
assert rejects([1], [1], -1), "negative cap rejected"
assert rejects([1], [1], 1.5), "fractional cap rejected"
print("ok")
