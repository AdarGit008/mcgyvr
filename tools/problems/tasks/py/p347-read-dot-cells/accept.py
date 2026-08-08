from solution import read_dot_cells


def rejects(value):
    try:
        read_dot_cells(value)
    except ValueError:
        return True
    return False


assert read_dot_cells("1") == "a", "weight one"
assert read_dot_cells("2") == "b", "weight two"
assert read_dot_cells("12") == "c", "two dots add up"
assert read_dot_cells("245") == "z", "the last letter"
assert read_dot_cells("134-234") == "mn", "two letters in the middle"
assert read_dot_cells("6-1") == "A", "the shift sign capitalises"
assert read_dot_cells("6-245") == "Z", "a capital at the far end"
assert read_dot_cells("0") == " ", "a blank cell is a space"
assert read_dot_cells("1-0-2") == "a b", "a space between letters"
assert read_dot_cells("6-1-0-2") == "A b", "shift, blank, then a letter"
assert read_dot_cells("56-1-12") == "13", "one count sign covers the whole run"
assert read_dot_cells("56-24") == "0", "weight ten is the digit zero"
assert read_dot_cells("56-1-0-1") == "1 a", "a blank cell closes the count"

assert rejects(42), "not a string"
assert rejects(""), "empty argument"
assert rejects("7"), "a dot beyond six"
assert rejects("11"), "a dot named twice"
assert rejects("21"), "dots that do not rise"
assert rejects("1245"), "a weight that spells nothing"
assert rejects("6"), "a shift sign ending the line"
assert rejects("6-0"), "a shift sign before a blank"
assert rejects("56-6"), "too heavy inside a count"
assert rejects("1--2"), "an empty cell"
print("ok")
