from solution import carry_kitty_shares

assert carry_kitty_shares(
    [{"cents": 10, "heads": 3}, {"cents": 0, "heads": 2}, {"cents": 7, "heads": 4}]
) == {
    "each": [3, 0, 2],
    "left": 0,
}, "the odd cent rides on until a later hop can break it up"
assert carry_kitty_shares([{"cents": 5, "heads": 2}, {"cents": 5, "heads": 2}]) == {
    "each": [2, 3],
    "left": 0,
}, "a carried cent lifts the next hop's bill"
assert carry_kitty_shares([{"cents": 1, "heads": 5}]) == {
    "each": [0],
    "left": 1,
}, "a hop too small to split bills nobody and keeps the lot"
assert carry_kitty_shares([{"cents": 99, "heads": 1}]) == {
    "each": [99],
    "left": 0,
}, "a lone walker is billed the whole hop"
assert carry_kitty_shares([{"cents": 0, "heads": 4}]) == {
    "each": [0],
    "left": 0,
}, "a free hop bills nothing and keeps nothing"
assert carry_kitty_shares([{"cents": 8, "heads": 3}, {"cents": 1, "heads": 4}]) == {
    "each": [2, 0],
    "left": 3,
}, "what the last hop cannot break up is still in the kitty at the end"
assert carry_kitty_shares([{"cents": 7, "heads": 2}, {"cents": 2, "heads": 3}]) == {
    "each": [3, 1],
    "left": 0,
}, "the group may shrink or swell between hops"


def rejects(hops):
    try:
        carry_kitty_shares(hops)
    except ValueError:
        return True
    return False


assert rejects([]), "a journey with no hops is rejected"
assert rejects("nope"), "a non-list argument is rejected"
assert rejects([{"cents": 5, "heads": 0}]), "a hop nobody walked is rejected"
assert rejects([{"cents": -5, "heads": 2}]), "a hop costing less than nothing is rejected"
assert rejects([{"cents": 5.5, "heads": 2}]), "cents that are not whole are rejected"
assert rejects([{"cents": 5, "heads": 2, "tip": 1}]), "a hop with a spare key is rejected"
assert rejects([{"cents": 5}]), "a hop with no head count is rejected"
print("ok")
