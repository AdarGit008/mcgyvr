from solution import pack_clue_line


def rejects(width, clues):
    try:
        pack_clue_line(width, clues)
    except ValueError:
        return True
    return False


assert pack_clue_line(7, []) == ".......", "no clues draws a bare width"
assert pack_clue_line(7, [3]) == "###....", "one group hugs the left edge"
assert pack_clue_line(7, [2, 1]) == "##.#...", "one dot parts the two groups"
assert pack_clue_line(7, [1, 1, 1]) == "#.#.#..", "three lone cells and their gaps"
assert pack_clue_line(7, [7]) == "#######", "a group filling the whole width"
assert pack_clue_line(5, [2, 2]) == "##.##", "a drawing that ends exactly at the edge"
assert pack_clue_line(1, [1]) == "#", "a width of one"
assert pack_clue_line(9, [4, 2]) == "####.##..", "the leftover tail is dots"
assert rejects(0, [1]), "a width of zero is rejected"
assert rejects(2.5, [1]), "a fractional width is rejected"
assert rejects(7, [0]), "a clue of zero is rejected"
assert rejects(4, [2, 2]), "a drawing wider than the line"
assert rejects(7, "3"), "a clue list that is not a list"
assert rejects(7, ["3"]), "a clue that is not a number"
print("ok")
