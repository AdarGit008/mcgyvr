from solution import number_grid_slots


def rejects(rows):
    try:
        number_grid_slots(rows)
    except ValueError:
        return True
    return False


assert number_grid_slots(["...", ".#.", "..."]) == [
    {"at": 1, "row": 0, "col": 0, "across": 3, "down": 3},
    {"at": 2, "row": 0, "col": 2, "across": 0, "down": 3},
    {"at": 3, "row": 2, "col": 0, "across": 3, "down": 0},
], "a square with a block in the middle"

assert number_grid_slots(["...#.", ".#...", ".....", "#...."]) == [
    {"at": 1, "row": 0, "col": 0, "across": 3, "down": 3},
    {"at": 2, "row": 0, "col": 2, "across": 0, "down": 4},
    {"at": 3, "row": 0, "col": 4, "across": 0, "down": 4},
    {"at": 4, "row": 1, "col": 2, "across": 3, "down": 0},
    {"at": 5, "row": 1, "col": 3, "across": 0, "down": 3},
    {"at": 6, "row": 2, "col": 0, "across": 5, "down": 0},
    {"at": 7, "row": 2, "col": 1, "across": 0, "down": 2},
    {"at": 8, "row": 3, "col": 1, "across": 4, "down": 0},
], "a ragged grid numbered right through"

assert number_grid_slots(["...."]) == [
    {"at": 1, "row": 0, "col": 0, "across": 4, "down": 0}
], "one row holds one across slot and no down slot"

assert number_grid_slots([".", ".", "."]) == [
    {"at": 1, "row": 0, "col": 0, "across": 0, "down": 3}
], "one column holds one down slot and no across slot"

assert number_grid_slots(["###"]) == [], "a wholly blocked grid numbers nothing"

assert number_grid_slots([".#.", "###", ".#."]) == [], "single open squares are too short to open anything"

assert number_grid_slots(["..#.."]) == [
    {"at": 1, "row": 0, "col": 0, "across": 2, "down": 0},
    {"at": 2, "row": 0, "col": 3, "across": 2, "down": 0},
], "a block starts the count again further along the row"

assert number_grid_slots(["..", ".."]) == [
    {"at": 1, "row": 0, "col": 0, "across": 2, "down": 2},
    {"at": 2, "row": 0, "col": 1, "across": 0, "down": 2},
    {"at": 3, "row": 1, "col": 0, "across": 2, "down": 0},
], "the smallest grid that opens slots both ways"

assert rejects([]), "an empty grid is rejected"
assert rejects("..."), "rows that are not a list are rejected"
assert rejects([5]), "a row that is not a string is rejected"
assert rejects([""]), "an empty row is rejected"
assert rejects(["..", "..."]), "rows of unlike length are rejected"
assert rejects(["..x"]), "a character that is neither open nor blocked is rejected"
assert rejects(["...", " .."]), "a space in the grid is rejected"

print("ok")
