from solution import first_clue_clash


def rejects(line, clues):
    try:
        first_clue_clash(line, clues)
    except ValueError:
        return True
    return False


assert first_clue_clash("##.#...", [2, 1]) == -1, "the runs match the clues"
assert first_clue_clash("##.#...", [2, 2]) == 1, "the second block is too short"
assert first_clue_clash("##.#...", [2]) == 1, "one block more than the clues want"
assert first_clue_clash("##.#...", [2, 1, 1]) == 2, "one clue more than the line has"
assert first_clue_clash(".......", []) == -1, "a bare line matches no clues"
assert first_clue_clash(".......", [1]) == 0, "a bare line fails its first clue"
assert first_clue_clash("###....", [3]) == -1, "a single block at the left"
assert first_clue_clash("....###", [3]) == -1, "a single block at the right"
assert first_clue_clash("#.#.#..", [1, 1, 1]) == -1, "three lone cells"
assert first_clue_clash("#.#.#..", [1, 2, 1]) == 1, "the middle clue disagrees"
assert first_clue_clash("#######", [7]) == -1, "the whole line is one block"
assert first_clue_clash("###.###", [3, 3]) == -1, "two blocks split by one dot"
assert first_clue_clash("#..###.", [2, 3]) == 0, "the very first place disagrees"
assert rejects("", []), "an empty line is rejected"
assert rejects("##x#...", [2, 1]), "a stray character is rejected"
assert rejects("##.#...", [0]), "a clue of zero is rejected"
assert rejects("##.#...", [2, -1]), "a negative clue is rejected"
assert rejects("##.#...", [4, 4]), "clues that cannot fit are rejected"
assert rejects("##.#...", 3), "a clue list that is not a list"
assert rejects(42, [1]), "a line that is not a string"
print("ok")
