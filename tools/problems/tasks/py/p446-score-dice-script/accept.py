from solution import score_dice_script


def rejects(script, rolls):
    try:
        score_dice_script(script, rolls)
    except ValueError:
        return True
    return False


assert score_dice_script("3", []) == 3, "a bare constant draws nothing"
assert score_dice_script("1d6", [4]) == 4, "one die, one roll"
assert score_dice_script("2d6+3", [5, 2]) == 10, "two dice and a constant"
assert score_dice_script("2d6-1d4", [6, 6, 3]) == 9, "a minus sign subtracts a whole group"
assert score_dice_script("1d6!", [6, 6, 2]) == 14, "an open-ended group keeps drawing"
assert score_dice_script("2d4!+1", [4, 1, 2]) == 8, "only the die that hit the size draws again"
assert score_dice_script("10+2d20-5", [20, 1]) == 26, "a closed group does not draw again on its size"
assert score_dice_script("1d12!", [12, 12, 12, 1]) == 37, "a chain of three open draws"
assert score_dice_script("1d4+1d6", [1, 6]) == 7, "each group checks the rolls against its own size"
assert score_dice_script("0+1d4", [2]) == 2, "a zero constant contributes nothing"
assert score_dice_script("20d4", [1] * 20) == 20, "the largest count is allowed"

assert rejects("", []), "an empty script is refused"
assert rejects(5, []), "a script that is not a string is refused"
assert rejects("1d6", "nope"), "rolls that are not a list are refused"
assert rejects("1d6", [7]), "a roll above the die size is refused"
assert rejects("1d6", [0]), "a roll below one is refused"
assert rejects("1d6", [2.5]), "a roll that is not whole is refused"
assert rejects("1d6", [3, 3]), "a leftover roll is refused"
assert rejects("2d6", [3]), "running out of rolls is refused"
assert rejects("1d7", [3]), "an unknown die size is refused"
assert rejects("0d6", []), "a count of zero is refused"
assert rejects("21d4", []), "a count above twenty is refused"
assert rejects("+1d6", [3]), "a leading sign is refused"
assert rejects("1d6+", [3]), "a trailing sign is refused"
assert rejects("1d6++1", [3]), "two signs running are refused"
assert rejects("1d6x2", [3]), "an unreadable term is refused"
assert rejects("1d6!!", [3]), "two exclamation marks are refused"
print("ok")
