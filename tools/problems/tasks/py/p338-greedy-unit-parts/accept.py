from solution import greedy_unit_parts

assert greedy_unit_parts(5, 6) == [2, 3], "five sixths splits into two pieces"
assert greedy_unit_parts(3, 7) == [3, 11, 231], "three sevenths takes three pieces"
assert greedy_unit_parts(1, 2) == [2], "a piece that already fits stays whole"
assert greedy_unit_parts(2, 3) == [2, 6], "two thirds splits into a half and a sixth"
assert greedy_unit_parts(4, 5) == [2, 4, 20], "four fifths takes three pieces"
assert greedy_unit_parts(9, 20) == [3, 9, 180], "nine twentieths takes three pieces"
assert greedy_unit_parts(1, 10000) == [
    10000
], "the smallest allowed quotient is already one piece"
assert greedy_unit_parts(4, 6) == [
    2,
    6,
], "a quotient handed over unreduced splits like its reduced form"

rising = greedy_unit_parts(9, 20)
for index in range(1, len(rising)):
    assert rising[index] > rising[index - 1], "the somethings rise strictly"


def rejects(top, bottom):
    try:
        greedy_unit_parts(top, bottom)
    except ValueError:
        return True
    return False


assert rejects(5, 121), "a quotient whose remainder explodes is rejected"
assert rejects(0, 5), "a top of nothing is rejected"
assert rejects(-1, 5), "a negative top is rejected"
assert rejects(5, 5), "a quotient of one is rejected"
assert rejects(7, 5), "a quotient above one is rejected"
assert rejects(1, 10001), "a bottom past the ceiling is rejected"
assert rejects(1, 0), "a bottom of nothing is rejected"
assert rejects(1.5, 4), "a fractional top is rejected"
assert rejects("1", 4), "a non-numeric top is rejected"
print("ok")
