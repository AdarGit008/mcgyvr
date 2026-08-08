from solution import assign_home_waves

WAVES = [
    {"name": "north", "home": "a", "cap": 2},
    {"name": "mid", "home": "b", "cap": 1},
    {"name": "south", "home": "c", "cap": 3},
]

assert assign_home_waves(
    WAVES,
    [
        {"ref": "r1", "zones": ["a"]},
        {"ref": "r2", "zones": ["b", "c"]},
        {"ref": "r3", "zones": ["b"]},
        {"ref": "r4", "zones": ["a", "c"]},
        {"ref": "r5", "zones": ["a"]},
        {"ref": "r6", "zones": ["d"]},
        {"ref": "r7", "zones": ["c", "a"]},
    ],
) == {
    "loads": [
        {"name": "north", "refs": ["r1", "r4"]},
        {"name": "mid", "refs": ["r2"]},
        {"name": "south", "refs": ["r7"]},
    ],
    "spill": ["r3", "r5", "r6"],
}, "the earliest suitable wave with room takes the order"
assert assign_home_waves(WAVES, []) == {
    "loads": [
        {"name": "north", "refs": []},
        {"name": "mid", "refs": []},
        {"name": "south", "refs": []},
    ],
    "spill": [],
}, "every standing wave is reported even when it carries nothing"
assert assign_home_waves(
    [{"name": "solo", "home": "z", "cap": 1}],
    [{"ref": "q1", "zones": ["z"]}, {"ref": "q2", "zones": ["z"]}],
) == {
    "loads": [{"name": "solo", "refs": ["q1"]}],
    "spill": ["q2"],
}, "a full wave sends the next order to the spill sheet"
assert assign_home_waves(WAVES, [{"ref": "s1", "zones": ["c", "b", "a"]}]) == {
    "loads": [
        {"name": "north", "refs": ["s1"]},
        {"name": "mid", "refs": []},
        {"name": "south", "refs": []},
    ],
    "spill": [],
}, "an order wanting three homes goes to the earliest released of them"
assert assign_home_waves(WAVES, [{"ref": "s2", "zones": ["e", "f"]}]) == {
    "loads": [
        {"name": "north", "refs": []},
        {"name": "mid", "refs": []},
        {"name": "south", "refs": []},
    ],
    "spill": ["s2"],
}, "an order wanting no home aisle spills at once"
assert assign_home_waves(
    [{"name": "wide", "home": "a", "cap": 3}],
    [{"ref": "t1", "zones": ["a"]}, {"ref": "t2", "zones": ["a"]}, {"ref": "t3", "zones": ["a"]}],
) == {
    "loads": [{"name": "wide", "refs": ["t1", "t2", "t3"]}],
    "spill": [],
}, "a cap is a ceiling, not a target"

ONE = [{"name": "n", "home": "a", "cap": 1}]


def rejects(waves, orders):
    try:
        assign_home_waves(waves, orders)
    except ValueError:
        return True
    return False


assert rejects([], []), "no standing waves at all"
assert rejects(["n"], []), "a wave must be a mapping"
assert rejects(
    [{"name": "n", "home": "a", "cap": 1}, {"name": "n", "home": "b", "cap": 1}], []
), "two waves may not share a name"
assert rejects(
    [{"name": "n", "home": "a", "cap": 1}, {"name": "m", "home": "a", "cap": 1}], []
), "two waves may not share a home"
assert rejects([{"name": "n", "home": "A", "cap": 1}], []), "a capital home"
assert rejects([{"name": "n", "home": "a", "cap": 0}], []), "a cap of zero"
assert rejects(ONE, "orders"), "the orders must be a list"
assert rejects(ONE, [{"ref": "x", "zones": ["a"]}, {"ref": "x", "zones": ["a"]}]), "a shared ref"
assert rejects(ONE, [{"ref": "x", "zones": []}]), "an order needs a zone"
assert rejects(ONE, [{"ref": "x", "zones": ["a", "a"]}]), "an aisle named twice"
print("ok")
