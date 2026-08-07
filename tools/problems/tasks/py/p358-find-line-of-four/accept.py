from solution import find_line_of_four

assert find_line_of_four(["....", "....", "....", "rrrr"]) == {
    "winner": "r",
    "cells": [[3, 0], [3, 1], [3, 2], [3, 3]],
}, "four along the floor"
assert find_line_of_four(["y...", "y...", "y...", "y..."]) == {
    "winner": "y",
    "cells": [[0, 0], [1, 0], [2, 0], [3, 0]],
}, "four stacked in one column"
assert find_line_of_four(["r...", "yr..", "yyr.", "yyyr"]) == {
    "winner": "r",
    "cells": [[0, 0], [1, 1], [2, 2], [3, 3]],
}, "four running down and right"
assert find_line_of_four(["...y", "..yr", ".yrr", "yrrr"]) == {
    "winner": "y",
    "cells": [[3, 0], [2, 1], [1, 2], [0, 3]],
}, "four running up and right"
assert find_line_of_four(["....", "....", "....", "ryry"]) == {
    "winner": "none",
    "cells": [],
}, "a floor of alternating marks wins nothing"
assert find_line_of_four(["....", "....", "....", "...."]) == {
    "winner": "none",
    "cells": [],
}, "a vacant board wins nothing"
assert find_line_of_four(["..", ".."]) == {
    "winner": "none",
    "cells": [],
}, "a board too small to hold four"
assert find_line_of_four(["....", "....", "rrrr", "yyyy"]) == {
    "winner": "r",
    "cells": [[2, 0], [2, 1], [2, 2], [2, 3]],
}, "the higher line is met first in the sweep"
assert find_line_of_four(["rrrr", "ryyy", "ryyy", "ryyy"]) == {
    "winner": "r",
    "cells": [[0, 0], [0, 1], [0, 2], [0, 3]],
}, "right is tried before down"


def rejects(board):
    try:
        find_line_of_four(board)
    except ValueError:
        return True
    return False


assert rejects("rrrr"), "a board that is not a list is thrown out"
assert rejects([]), "a board with no lines is thrown out"
assert rejects([["r"]]), "a line that is not a string is thrown out"
assert rejects(["rr", ""]), "an empty line is thrown out"
assert rejects(["rr", "rrr"]), "lines of unequal length are thrown out"
assert rejects(["rb.."]), "a mark outside r, y and the dot is thrown out"
assert rejects(["r...", "...."]), "a hanging disc is thrown out"
assert rejects(["r.", ".r"]), "a disc over a vacant square is thrown out"
print("ok")
