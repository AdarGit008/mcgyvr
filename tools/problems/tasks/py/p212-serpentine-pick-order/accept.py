from solution import serpentine_pick_order


def pick(sku, aisle, bay):
    return {"sku": sku, "aisle": aisle, "bay": bay}


def rejects(value):
    try:
        serpentine_pick_order(value)
    except ValueError:
        return True
    return False


assert serpentine_pick_order([]) == [], "nothing to grab"
assert serpentine_pick_order([pick("a", 1, 4)]) == ["a"], "a lone pick"
assert serpentine_pick_order(
    [pick("a", 1, 9), pick("b", 1, 2), pick("c", 1, 5)]
) == ["b", "c", "a"], "an odd aisle climbs the bays"
assert serpentine_pick_order(
    [pick("a", 2, 9), pick("b", 2, 2), pick("c", 2, 5)]
) == ["a", "c", "b"], "an even aisle descends the bays"
assert serpentine_pick_order(
    [pick("x", 3, 1), pick("y", 2, 1), pick("z", 1, 1)]
) == ["z", "y", "x"], "aisles are worked in ascending order"
assert serpentine_pick_order(
    [pick("p", 1, 2), pick("q", 2, 3), pick("r", 1, 7), pick("s", 2, 8)]
) == ["p", "r", "s", "q"], "the walk turns at the end of each aisle"
assert serpentine_pick_order([pick("late", 4, 5), pick("early", 4, 5)]) == [
    "late",
    "early",
], "a shared bay keeps the listed order"
assert serpentine_pick_order(
    [pick("m", 6, 1), pick("n", 5, 3), pick("o", 6, 4), pick("p", 5, 1)]
) == ["p", "n", "o", "m"], "two aisles of opposite parity"

assert rejects("nope"), "a pick list that is not a list is rejected"
assert rejects([[1, 2]]), "a pick that is not a mapping is rejected"
assert rejects([{"aisle": 1, "bay": 1}]), "a missing sku is rejected"
assert rejects([pick("", 1, 1)]), "an empty sku is rejected"
assert rejects([pick("a", 1, 1), pick("a", 2, 2)]), "a repeated sku is rejected"
assert rejects([pick("a", 0, 1)]), "aisle zero is rejected"
assert rejects([pick("a", 1, -2)]), "a negative bay is rejected"

print("ok")
