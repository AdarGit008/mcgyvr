from solution import mend_row_blocks

sheet = ["r1", "r2", "r3", "r4", "r5"]

assert mend_row_blocks(sheet, []) == {
    "rows": ["r1", "r2", "r3", "r4", "r5"],
    "rejected": [],
}, "no blocks leaves the sheet alone"
assert mend_row_blocks(sheet, [{"start": 2, "drop": 1, "insert": ["R2"], "guard": "r2"}]) == {
    "rows": ["r1", "R2", "r3", "r4", "r5"],
    "rejected": [],
}, "one row swapped for one row"
assert mend_row_blocks(sheet, [{"start": 3, "drop": 0, "insert": ["x"], "guard": "r3"}]) == {
    "rows": ["r1", "r2", "x", "r3", "r4", "r5"],
    "rejected": [],
}, "a block that drops nothing pushes its rows in ahead of start"
assert mend_row_blocks(sheet, [{"start": 6, "drop": 0, "insert": ["r6"], "guard": None}]) == {
    "rows": ["r1", "r2", "r3", "r4", "r5", "r6"],
    "rejected": [],
}, "a start one past the sheet adds at the foot"
assert mend_row_blocks(
    sheet,
    [
        {"start": 1, "drop": 1, "insert": ["A", "B"], "guard": "r1"},
        {"start": 4, "drop": 1, "insert": ["D"], "guard": "r4"},
    ],
) == {
    "rows": ["A", "B", "r2", "r3", "D", "r5"],
    "rejected": [],
}, "a block that grew the sheet does not drag the next one along"
assert mend_row_blocks(
    sheet,
    [
        {"start": 1, "drop": 2, "insert": [], "guard": "r1"},
        {"start": 4, "drop": 1, "insert": ["D"], "guard": "r4"},
    ],
) == {
    "rows": ["r3", "D", "r5"],
    "rejected": [],
}, "a block that shrank the sheet does not drag the next one back"
assert mend_row_blocks(
    sheet,
    [
        {"start": 1, "drop": 1, "insert": ["A", "B"], "guard": "r1"},
        {"start": 3, "drop": 1, "insert": ["C"], "guard": "nope"},
        {"start": 5, "drop": 1, "insert": ["E"], "guard": "r5"},
    ],
) == {
    "rows": ["A", "B", "r2", "r3", "r4", "E"],
    "rejected": [1],
}, "a turned-away block adds no offset of its own"
assert mend_row_blocks(sheet, [{"start": 2, "drop": 1, "insert": ["X"], "guard": "nope"}]) == {
    "rows": ["r1", "r2", "r3", "r4", "r5"],
    "rejected": [0],
}, "a guard that names the wrong row turns the block away"
assert mend_row_blocks(sheet, [{"start": 5, "drop": 3, "insert": [], "guard": "r5"}]) == {
    "rows": ["r1", "r2", "r3", "r4", "r5"],
    "rejected": [0],
}, "a reach past the foot of the sheet turns the block away"
assert mend_row_blocks([], [{"start": 1, "drop": 0, "insert": ["only"], "guard": None}]) == {
    "rows": ["only"],
    "rejected": [],
}, "an empty sheet may still be written into"


def rejects(rows, blocks):
    try:
        mend_row_blocks(rows, blocks)
    except ValueError:
        return True
    return False


assert rejects(sheet, [{"start": 0, "drop": 0, "insert": [], "guard": None}]), "a start below one is refused"
assert rejects(sheet, [{"start": 1, "drop": -1, "insert": [], "guard": None}]), "a drop below none is refused"
assert rejects(
    sheet, [{"start": 1, "drop": 0, "insert": [], "guard": 7}]
), "a guard that is neither null nor a string is refused"
assert rejects(
    sheet,
    [{"start": 3, "drop": 0, "insert": [], "guard": None}, {"start": 2, "drop": 0, "insert": [], "guard": None}],
), "starts that do not climb are refused"
assert rejects(
    sheet,
    [{"start": 1, "drop": 2, "insert": [], "guard": None}, {"start": 2, "drop": 0, "insert": [], "guard": None}],
), "a block reaching into the next is refused"
assert rejects(sheet, [{"start": 1, "drop": 0, "insert": "row", "guard": None}]), "an insert that is not a list is refused"
assert rejects(["a", 2], []), "a sheet holding a non-string is refused"
assert rejects(sheet, ["block"]), "a block that is not a mapping is refused"
print("ok")
