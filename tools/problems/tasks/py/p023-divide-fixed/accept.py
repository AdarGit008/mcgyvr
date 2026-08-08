from solution import divide_fixed

assert divide_fixed(1, 8, 3) == "0.125", "exact quotient"
assert divide_fixed(1, 8, 2) == "0.12", "tie rounds to even (down)"
assert divide_fixed(3, 8, 2) == "0.38", "tie rounds to even (up)"
assert divide_fixed(7, 2, 0) == "4", "integer tie rounds to even, no point"
assert divide_fixed(5, 2, 0) == "2", "integer tie rounds down to even"
assert divide_fixed(1, 3, 4) == "0.3333", "repeating decimal truncated side"
assert divide_fixed(2, 3, 4) == "0.6667", "non-tie rounds up normally"
assert divide_fixed(-1, 8, 2) == "-0.12", "negative quotient keeps its sign"
assert divide_fixed(-7, 2, 0) == "-4", "negative integer tie to even"
assert divide_fixed(-1, 200, 2) == "0.00", "zero result never shows a minus"
assert divide_fixed(10, 4, 1) == "2.5", "exact one-place result"
assert divide_fixed(3, -2, 1) == "-1.5", "negative denominator flips sign"
assert divide_fixed(1200, 4, 2) == "300.00", "padding after the point"


def rejects(*args):
    try:
        divide_fixed(*args)
    except ValueError:
        return True
    return False


assert rejects(1, 0, 2), "zero denominator is rejected"
assert rejects(1, 2, -1), "negative places is rejected"
assert rejects(1, 2, 7), "places above 6 is rejected"
assert rejects(1.5, 2, 2), "fractional numerator is rejected"
assert rejects("1", 2, 2), "non-number argument is rejected"
print("ok")
