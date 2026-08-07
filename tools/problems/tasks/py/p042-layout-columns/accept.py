from solution import layout_columns

assert layout_columns([["a", "bb"], ["ccc", "d"]], "ll") == [
    "a    bb",
    "ccc  d",
], "left alignment pads to the widest cell"
assert layout_columns([["a", "bb"], ["ccc", "d"]], "rr") == [
    "  a  bb",
    "ccc   d",
], "right alignment pads on the left"
assert layout_columns([["ab"], ["wxyz"]], "c") == [
    " ab",
    "wxyz",
], "centering gives the odd space to the right, then trims it"
assert layout_columns([["a"], ["abcde"]], "c") == [
    "  a",
    "abcde",
], "even centering splits padding equally"
assert layout_columns([["x", "y"]], "lr") == [
    "x  y"
], "columns are separated by exactly two spaces"
assert layout_columns([["hi", "a"], ["z", "b"]], "ll") == [
    "hi  a",
    "z   b",
], "no trailing whitespace survives on any line"
assert layout_columns([["", "x"], ["yy", "z"]], "rl") == [
    "    x",
    "yy  z",
], "an empty cell still occupies its column width"


def rejects(rows, aligns):
    try:
        layout_columns(rows, aligns)
    except ValueError:
        return True
    return False


assert rejects([], "l"), "empty table is rejected"
assert rejects([["a", "b"], ["c"]], "ll"), "ragged row is rejected"
assert rejects([["a"]], "x"), "unknown alignment character is rejected"
assert rejects([["a", "b"]], "l"), "spec shorter than the rows is rejected"
assert rejects([[42]], "l"), "non-string cell is rejected"
print("ok")
