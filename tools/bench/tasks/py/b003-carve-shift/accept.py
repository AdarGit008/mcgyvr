from solution import carve_shift

assert carve_shift(0, 10, 4, 2, 1) == [[0, 4], [6, 10]], "two stretches"
assert carve_shift(5, 8, 10, 3, 1) == [[5, 8]], "shift shorter than span"
assert carve_shift(0, 7, 4, 2, 2) == [[0, 4]], "short tail is dropped"
assert carve_shift(0, 9, 4, 2, 3) == [
    [0, 4],
    [6, 9],
], "tail of exactly least units is kept"
assert carve_shift(0, 12, 4, 2, 1) == [
    [0, 4],
    [6, 10],
], "a rest may swallow the end of the shift"
assert carve_shift(-6, 3, 5, 1, 2) == [[-6, -1], [0, 3]], "negative bounds"


def rejects(*args):
    try:
        carve_shift(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 10, 2.5, 1, 1), "fractional span"
assert rejects(0, 10, 4, 0, 1), "rest below one"
assert rejects(3, 3, 1, 1, 1), "empty shift is rejected"
assert rejects(5, 2, 1, 1, 1), "reversed shift is rejected"
assert rejects(0, 10, 0, 1, 1), "span below one"
assert rejects(0, 10, 3, 1, 4), "least above span"
print("ok")
