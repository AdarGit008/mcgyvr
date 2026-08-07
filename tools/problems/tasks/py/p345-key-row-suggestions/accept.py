from solution import key_row_suggestions

BOARD = ["qwert", "asdfg", "zxcvb"]


def rejects(*args):
    try:
        key_row_suggestions(*args)
    except ValueError:
        return True
    return False


assert key_row_suggestions(BOARD, "sat", ["cat", "wat", "zat", "dat", "fat"]) == [
    "dat",
    "wat",
    "zat",
    "cat",
], "compass order, and a two-column gap never touches"
assert key_row_suggestions(BOARD, "df", ["sf", "ff"]) == ["sf", "ff"], (
    "straight left comes before straight right"
)
assert key_row_suggestions(BOARD, "ss", ["ds", "sd"]) == ["ds", "sd"], (
    "the same step is ordered leftmost place first"
)
assert key_row_suggestions(BOARD, "cat", ["cat", "bat"]) == [], (
    "an accepted typed word yields nothing"
)
assert key_row_suggestions(BOARD, "qq", ["zz"]) == [], (
    "no accepted word is one step away"
)
assert key_row_suggestions(["ab", "cde"], "ae", ["be", "ab"]) == ["be", "ab"], (
    "ragged rows and a diagonal step"
)

assert rejects("qwert", "sat", ["cat"]), "not a list"
assert rejects([], "sat", ["cat"]), "no rows"
assert rejects(["qwe", ""], "q", ["w"]), "empty row"
assert rejects(["QWE"], "q", ["w"]), "uppercase row"
assert rejects(["qw", "wa"], "q", ["w"]), "letter drawn twice"
assert rejects(BOARD, "", ["cat"]), "empty typed word"
assert rejects(BOARD, "Sat", ["cat"]), "uppercase typed"
assert rejects(BOARD, "sap", ["cat"]), "letter off the drawing"
assert rejects(BOARD, "sat", "cat"), "accepted not a list"
assert rejects(BOARD, "sat", [""]), "empty accepted word"
print("ok")
