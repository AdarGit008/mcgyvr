from solution import level_strip

assert level_strip([0, 1, 2, 3], 0, 8, ".:*#") == "..::", "lower bands floor down"
assert level_strip([4, 5, 6, 7], 0, 8, ".:*#") == "**##", "upper bands floor down"
assert level_strip([-5], 0, 8, ".:*#") == ".", "below the span clamps dimmest"
assert level_strip([8, 99], 0, 8, ".:*#") == "##", "at or beyond high clamps brightest"
assert level_strip([10, 12, 13], 10, 14, "ab") == "abb", "a nonzero low shifts the bands"
assert level_strip([], 0, 8, ".:*#") == "", "no readings, empty strip"
assert level_strip([3, -9, 42], 5, 6, "o") == "ooo", (
    "one-character ramp absorbs everything"
)


def rejects(readings, low, high, ramp):
    try:
        level_strip(readings, low, high, ramp)
    except ValueError:
        return True
    return False


assert rejects([1], 0, 8, ""), "empty ramp is rejected"
assert rejects([1], 5, 5, ".:*#"), "flat span is rejected"
assert rejects([1], 9, 2, ".:*#"), "inverted span is rejected"
print("ok")
