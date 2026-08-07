from solution import build_pick_waves

DAY = [
    {"ref": "o1", "lines": 4, "zones": ["a"]},
    {"ref": "o2", "lines": 3, "zones": ["b"]},
    {"ref": "o3", "lines": 2, "zones": ["c"]},
    {"ref": "o4", "lines": 9, "zones": ["c"]},
    {"ref": "o5", "lines": 12, "zones": ["a"]},
    {"ref": "o6", "lines": 1, "zones": ["a", "b", "c"]},
    {"ref": "o7", "lines": 1, "zones": ["c"]},
    {"ref": "o8", "lines": 1, "zones": ["c"]},
    {"ref": "o9", "lines": 1, "zones": ["c"]},
    {"ref": "o10", "lines": 1, "zones": ["d"]},
    {"ref": "o11", "lines": 1, "zones": ["c"]},
]

assert build_pick_waves(DAY, {"lines": 10, "orders": 3, "zones": 2}) == {
    "waves": [
        {"name": "w1", "refs": ["o1", "o2"], "lines": 7, "zones": ["a", "b"]},
        {"name": "w2", "refs": ["o3"], "lines": 2, "zones": ["c"]},
        {"name": "w3", "refs": ["o4", "o7"], "lines": 10, "zones": ["c"]},
        {"name": "w4", "refs": ["o8", "o9", "o10"], "lines": 3, "zones": ["c", "d"]},
        {"name": "w5", "refs": ["o11"], "lines": 1, "zones": ["c"]},
    ],
    "refused": ["o5", "o6"],
}, "all three limits bite in turn and the refusals leave the open wave alone"
assert build_pick_waves([], {"lines": 5, "orders": 2, "zones": 1}) == {
    "waves": [],
    "refused": [],
}, "no orders release no waves"
assert build_pick_waves(
    [{"ref": "a1", "lines": 2, "zones": ["b", "a"]}], {"lines": 9, "orders": 9, "zones": 9}
) == {
    "waves": [{"name": "w1", "refs": ["a1"], "lines": 2, "zones": ["a", "b"]}],
    "refused": [],
}, "a wave's letters come out alphabetical"
assert build_pick_waves(DAY[:2], {"lines": 100, "orders": 100, "zones": 6}) == {
    "waves": [{"name": "w1", "refs": ["o1", "o2"], "lines": 7, "zones": ["a", "b"]}],
    "refused": [],
}, "generous limits keep everything in one wave"
assert build_pick_waves(
    [
        {"ref": "x1", "lines": 5, "zones": ["e"]},
        {"ref": "x2", "lines": 5, "zones": ["e"]},
        {"ref": "x3", "lines": 5, "zones": ["e"]},
    ],
    {"lines": 5, "orders": 4, "zones": 1},
) == {
    "waves": [
        {"name": "w1", "refs": ["x1"], "lines": 5, "zones": ["e"]},
        {"name": "w2", "refs": ["x2"], "lines": 5, "zones": ["e"]},
        {"name": "w3", "refs": ["x3"], "lines": 5, "zones": ["e"]},
    ],
    "refused": [],
}, "an order filling the line limit exactly still opens its own wave next time"
assert build_pick_waves(
    [
        {"ref": "y1", "lines": 1, "zones": ["a", "b"]},
        {"ref": "y2", "lines": 1, "zones": ["b", "c"]},
    ],
    {"lines": 9, "orders": 9, "zones": 3},
) == {
    "waves": [{"name": "w1", "refs": ["y1", "y2"], "lines": 2, "zones": ["a", "b", "c"]}],
    "refused": [],
}, "letters shared between orders are counted once"

LIMITS = {"lines": 5, "orders": 2, "zones": 2}


def rejects(orders, limits):
    try:
        build_pick_waves(orders, limits)
    except ValueError:
        return True
    return False


assert rejects(DAY, []), "the limits must be a mapping"
assert rejects(DAY, {"lines": 0, "orders": 2, "zones": 2}), "a limit of zero"
assert rejects("orders", LIMITS), "the orders must be a list"
assert rejects(["o1"], LIMITS), "an order must be a mapping"
assert rejects(
    [{"ref": "a", "lines": 1, "zones": ["a"]}, {"ref": "a", "lines": 1, "zones": ["a"]}], LIMITS
), "two orders may not share a ref"
assert rejects([{"ref": "a", "lines": 1.5, "zones": ["a"]}], LIMITS), "lines must be whole"
assert rejects([{"ref": "a", "lines": 1, "zones": []}], LIMITS), "an order needs a zone"
assert rejects([{"ref": "a", "lines": 1, "zones": ["g"]}], LIMITS), "a letter past f"
assert rejects([{"ref": "a", "lines": 1, "zones": ["a", "a"]}], LIMITS), "a repeated zone"
print("ok")
