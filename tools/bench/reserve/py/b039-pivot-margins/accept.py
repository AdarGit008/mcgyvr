from solution import pivot_margins


def table(rows, cols, cells, row_totals, col_totals, grand, blanks, leaders):
    return {
        "rows": rows,
        "cols": cols,
        "cells": cells,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "grand": grand,
        "blanks": blanks,
        "leaders": leaders,
    }


assert pivot_margins([]) == table(
    [], [], [], [], [], 0, 0, []
), "no entries yields an empty table"
assert pivot_margins([["north", "q1", 5]]) == table(
    ["north"], ["q1"], [[5]], [5], [5], 5, 0, ["q1"]
), "a single entry is a one-cell table"
assert pivot_margins([["north", "q1", 2], ["north", "q1", 3]])["cells"] == [
    [5]
], "entries on the same cell accumulate"
assert pivot_margins(
    [["north", "q1", 1], ["north", "q2", 2], ["south", "q1", 3], ["south", "q2", 4]]
) == table(
    ["south", "north"],
    ["q2", "q1"],
    [[4, 3], [2, 1]],
    [7, 3],
    [6, 4],
    10,
    0,
    ["q2", "q2"],
), "rows and cols both come back ordered by descending total"
assert pivot_margins([["a", "x", 1], ["b", "y", 2]]) == table(
    ["b", "a"], ["y", "x"], [[2, 0], [0, 1]], [2, 1], [2, 1], 3, 2, ["y", "x"]
), "cells with no entry read zero and count as blanks"
assert pivot_margins([["beta", "x", 5], ["alpha", "x", 5]])["rows"] == [
    "alpha",
    "beta",
], "a row total tie is broken alphabetically"
assert pivot_margins([["a", "x", 5], ["a", "x", -5], ["a", "y", 3]]) == table(
    ["a"], ["y", "x"], [[3, 0]], [3], [3, 0], 3, 0, ["y"]
), "a cell cancelling to zero is not blank"
assert pivot_margins([["r", "zeta", 5], ["r", "alpha", 5]]) == table(
    ["r"], ["alpha", "zeta"], [[5, 5]], [10], [5, 5], 10, 0, ["alpha"]
), "a column tie is alphabetical and a leader tie takes the leftmost"
assert pivot_margins(
    [
        ["west", "food", 4],
        ["east", "food", 1],
        ["west", "fuel", 2],
        ["mid", "fuel", 7],
        ["east", "food", 2],
    ]
) == table(
    ["mid", "west", "east"],
    ["fuel", "food"],
    [[7, 0], [2, 4], [0, 3]],
    [7, 6, 3],
    [9, 7],
    16,
    2,
    ["fuel", "food", "food"],
), "a three-by-two pivot with holes, ordering and leaders"
assert pivot_margins([["low", "x", 1], ["high", "x", 9]])["rows"] == [
    "high",
    "low",
], "the larger row total comes first"
assert pivot_margins([["r", "a", 1], ["r", "b", 2], ["r", "c", 3]]) == table(
    ["r"], ["c", "b", "a"], [[3, 2, 1]], [6], [3, 2, 1], 6, 0, ["c"]
), "one row across three columns orders columns by total"
assert pivot_margins([["a", "c", 2], ["b", "c", 2]]) == table(
    ["a", "b"], ["c"], [[2], [2]], [2, 2], [4], 4, 0, ["c", "c"]
), "one column across two tied rows"
assert pivot_margins([["neg", "x", -4], ["pos", "x", 3]]) == table(
    ["pos", "neg"], ["x"], [[3], [-4]], [3, -4], [-1], -1, 0, ["x", "x"]
), "negative amounts rank below positive ones"


def rejects(entries):
    try:
        pivot_margins(entries)
    except Exception:
        return True
    return False


assert rejects("x"), "non-list entries is rejected"
assert rejects([["a", "b"]]), "a two-item entry is rejected"
assert rejects([["", "c", 1]]), "an empty row label is rejected"
assert rejects([[7, "c", 1]]), "a non-string row label is rejected"
assert rejects([["r", "", 1]]), "an empty column label is rejected"
assert rejects([["r", "c", 2.5]]), "a fractional amount is rejected"
assert rejects([["r", "c", "5"]]), "a string amount is rejected"
print("ok")
