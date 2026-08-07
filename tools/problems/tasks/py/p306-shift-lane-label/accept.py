from solution import shift_lane_label


def rejects(label, step):
    try:
        shift_lane_label(label, step)
    except ValueError:
        return True
    return False


assert shift_lane_label("A", 1) == "B", "one place right of the first lane"
assert shift_lane_label("B", 0) == "B", "nought leaves the label alone"
assert shift_lane_label("A", 25) == "Z", "twenty-five places reach Z"
assert shift_lane_label("Z", 1) == "AA", "past Z the lettering grows"
assert shift_lane_label("A", 26) == "AA", "AA is the twenty-seventh lane"
assert shift_lane_label("AA", -1) == "Z", "and back again"
assert shift_lane_label("AZ", 1) == "BA", "AZ rolls into BA"
assert shift_lane_label("ZZ", 1) == "AAA", "ZZ rolls into three capitals"
assert shift_lane_label("AAA", -1) == "ZZ", "and back down to two"
assert shift_lane_label("C", -2) == "A", "a leftward step reaches the first lane"
assert shift_lane_label("ZZZ", 0) == "ZZZ", "the last lane stands still"
assert shift_lane_label("A", 18277) == "ZZZ", "the whole board in one step"

assert rejects("A", -1), "there is nothing left of the first lane"
assert rejects("ZZZ", 1), "there is nothing right of the last lane"
assert rejects("a", 1), "lower case is refused"
assert rejects("", 1), "a blank label is refused"
assert rejects("A1", 1), "a figure is not a capital"
assert rejects("AAAA", 0), "four capitals overrun the board"
assert rejects("A", 1.5), "a fractional step is refused"
assert rejects(5, 1), "a number is not a label"
print("ok")
