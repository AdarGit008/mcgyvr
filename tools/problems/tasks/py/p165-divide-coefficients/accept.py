from solution import divide_coefficients

assert divide_coefficients([-1, 0, 1], [-1, 1]) == [[1, 1], []], "clean division"
assert divide_coefficients([2, 3, 1], [1, 1]) == [[2, 1], []], "two roots"
assert divide_coefficients([1, 0, 0, 1], [0, 1]) == [
    [0, 0, 1],
    [1],
], "leftover survives"
assert divide_coefficients([4, 8], [2]) == [[2, 4], []], "constant divisor"
assert divide_coefficients([6, -5, 1], [-2, 1]) == [[-3, 1], []], "negatives"
assert divide_coefficients([1, 0, 4], [1, 2]) == [
    [-1, 2],
    [2],
], "quotient turns negative mid-way"
assert divide_coefficients([1, 2], [1, 0, 1]) == [[], [1, 2]], "divisor is longer"
assert divide_coefficients([], [1, 1]) == [[], []], "nothing to divide"


def rejects(dividend, divisor):
    try:
        divide_coefficients(dividend, divisor)
    except ValueError:
        return True
    return False


assert rejects([0, 0, 1], [1, 2]), "inexact leading step rejected"
assert rejects([0, 1, 1], [0, 3]), "leading coefficient does not divide"
assert rejects([1, 1], []), "empty divisor rejected"
assert rejects([1, 0], [1]), "trailing zero rejected"
assert rejects([1.5], [1]), "fraction rejected"
assert rejects("t", [1]), "non-list rejected"
print("ok")
