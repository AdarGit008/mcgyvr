from solution import resolve_dice_pool


def rejects(pools, rolls):
    try:
        resolve_dice_pool(pools, rolls)
    except ValueError:
        return True
    return False


assert resolve_dice_pool([{"sides": 6, "dice": 4, "keep": 3}], [3, 6, 1, 5]) == {
    "totals": [14],
    "dropped": [[2]],
}, "the three largest of four are held"
assert resolve_dice_pool([{"sides": 6, "dice": 3, "keep": 1}], [4, 4, 2]) == {
    "totals": [4],
    "dropped": [[1, 2]],
}, "equal rolls give the place to the one drawn earlier"
assert resolve_dice_pool(
    [{"sides": 6, "dice": 4, "keep": 3}, {"sides": 6, "dice": 3, "keep": 1}],
    [3, 6, 1, 5, 4, 4, 2],
) == {
    "totals": [14, 4],
    "dropped": [[2], [5, 6]],
}, "positions are counted across the whole roll list"
assert resolve_dice_pool([{"sides": 4, "dice": 2, "keep": 2}], [1, 4]) == {
    "totals": [5],
    "dropped": [[]],
}, "a pool that holds everything sets nothing aside"
assert resolve_dice_pool([{"sides": 20, "dice": 1, "keep": 1}], [13]) == {
    "totals": [13],
    "dropped": [[]],
}, "a single die"
assert resolve_dice_pool([{"sides": 6, "dice": 4, "keep": 2}], [5, 5, 5, 1]) == {
    "totals": [10],
    "dropped": [[2, 3]],
}, "three equal rolls and only two places"
assert resolve_dice_pool([{"sides": 3, "dice": 3, "keep": 2}], [3, 1, 3]) == {
    "totals": [6],
    "dropped": [[1]],
}, "an odd die size is allowed"

assert rejects(5, [1]), "pools that are not a list are refused"
assert rejects([], []), "an empty list of pools is refused"
assert rejects([{"sides": 6, "dice": 2, "keep": 3}], [1, 2]), "holding more dice than were thrown is refused"
assert rejects([{"sides": 6, "dice": 2, "keep": 0}], [1, 2]), "holding none is refused"
assert rejects([{"sides": 6, "dice": 0, "keep": 1}], []), "a pool of no dice is refused"
assert rejects([{"sides": 1, "dice": 1, "keep": 1}], [1]), "a one-sided die is refused"
assert rejects([{"sides": 6, "dice": 1, "keep": 1}], [7]), "a roll above the die size is refused"
assert rejects([{"sides": 6, "dice": 1, "keep": 1}], [0]), "a roll below one is refused"
assert rejects([{"sides": 6, "dice": 1, "keep": 1}], [3.5]), "a roll that is not whole is refused"
assert rejects([{"sides": 6, "dice": 3, "keep": 1}], [1, 2]), "running out of rolls is refused"
assert rejects([{"sides": 6, "dice": 1, "keep": 1}], [1, 2]), "a roll left undrawn is refused"
print("ok")
