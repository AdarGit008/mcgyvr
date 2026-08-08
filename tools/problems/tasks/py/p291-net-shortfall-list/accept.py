from solution import net_requirements

BENCH = [
    {"item": "desk", "needs": [{"item": "top", "per": 1}, {"item": "leg", "per": 4}]},
    {"item": "leg", "needs": [{"item": "dowel", "per": 2}, {"item": "cap", "per": 1}]},
]

assert net_requirements(BENCH, [], "desk", 1) == [
    {"item": "cap", "buy": 4},
    {"item": "dowel", "buy": 8},
    {"item": "top", "buy": 1},
], "an empty store buys the whole tree in"
assert net_requirements(
    BENCH, [{"item": "leg", "held": 2}, {"item": "dowel", "held": 3}], "desk", 1
) == [
    {"item": "cap", "buy": 2},
    {"item": "dowel", "buy": 1},
    {"item": "top", "buy": 1},
], "held sub-assemblies shrink what is made beneath them"
assert (
    net_requirements(
        BENCH, [{"item": "leg", "held": 4}, {"item": "top", "held": 1}], "desk", 1
    )
    == []
), "a store that covers every call buys nothing"
assert net_requirements(BENCH, [{"item": "desk", "held": 99}], "desk", 1) == [
    {"item": "cap", "buy": 4},
    {"item": "dowel", "buy": 8},
    {"item": "top", "buy": 1},
], "stock of the target itself is passed over"
assert net_requirements(
    [
        {"item": "kit", "needs": [{"item": "boxA", "per": 1}, {"item": "boxB", "per": 1}]},
        {"item": "boxA", "needs": [{"item": "nail", "per": 5}]},
        {"item": "boxB", "needs": [{"item": "nail", "per": 5}]},
    ],
    [{"item": "nail", "held": 6}],
    "kit",
    1,
) == [
    {"item": "nail", "buy": 4}
], "the first branch reached draws the store down before the second"
assert net_requirements(BENCH, [{"item": "cap", "held": 1}], "leg", 3) == [
    {"item": "cap", "buy": 2},
    {"item": "dowel", "buy": 6},
], "any made item may be the target"
assert net_requirements(BENCH, [{"item": "screw", "held": 40}], "screw", 7) == [
    {"item": "screw", "buy": 7}
], "a bought-in target stands for its whole batch"
assert net_requirements(BENCH, [], "desk", 2) == [
    {"item": "cap", "buy": 8},
    {"item": "dowel", "buy": 16},
    {"item": "top", "buy": 2},
], "the batch carries down every branch"


def rejects(recipes, stock, target, batch):
    try:
        net_requirements(recipes, stock, target, batch)
    except ValueError:
        return True
    return False


assert rejects(
    [
        {"item": "a", "needs": [{"item": "b", "per": 1}]},
        {"item": "b", "needs": [{"item": "a", "per": 1}]},
    ],
    [],
    "a",
    1,
), "a two-item loop"
assert rejects([{"item": "a", "needs": [{"item": "a", "per": 1}]}], [], "a", 1), (
    "an item made of itself"
)
assert rejects("no", [], "a", 1), "recipes is not a list"
assert rejects(BENCH, "no", "desk", 1), "stock is not a list"
assert rejects(
    [
        {"item": "a", "needs": [{"item": "b", "per": 1}]},
        {"item": "a", "needs": [{"item": "c", "per": 1}]},
    ],
    [],
    "a",
    1,
), "the same recipe twice"
assert rejects(
    BENCH, [{"item": "cap", "held": 1}, {"item": "cap", "held": 2}], "desk", 1
), "the same shelf twice"
assert rejects(BENCH, [{"item": "cap", "held": -1}], "desk", 1), (
    "a store holding less than nothing"
)
assert rejects([{"item": "a", "needs": []}], [], "a", 1), "a recipe that needs nothing"
assert rejects(
    [{"item": "a", "needs": [{"item": "b", "per": 1}, {"item": "b", "per": 2}]}],
    [],
    "a",
    1,
), "one need written twice"
assert rejects([{"item": "a", "needs": [{"item": "b", "per": 0}]}], [], "a", 1), (
    "a per of nothing"
)
assert rejects(BENCH, [], "", 1), "an empty target"
assert rejects(BENCH, [], "desk", 0), "a batch of none"
print("ok")
