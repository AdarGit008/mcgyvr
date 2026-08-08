from solution import build_replenishment_plan

assert build_replenishment_plan(
    {"held": 10, "floor": 4, "ceiling": 20, "pack": 5, "lead": 2, "inbound": []},
    [3, 3, 3, 3, 3],
) == {
    "orders": [{"week": 2, "units": 20}],
    "missed": 0,
    "closing": 15,
}, "a steady draw trips the floor once and lands two weeks later"

assert build_replenishment_plan(
    {"held": 2, "floor": 0, "ceiling": 6, "pack": 1, "lead": 3, "inbound": []},
    [5, 1, 1, 1],
) == {
    "orders": [{"week": 1, "units": 6}],
    "missed": 5,
    "closing": 5,
}, "a long lead leaves the depot missing draws week after week"

assert build_replenishment_plan(
    {
        "held": 0,
        "floor": 2,
        "ceiling": 10,
        "pack": 4,
        "lead": 1,
        "inbound": [{"week": 2, "units": 8}],
    },
    [0, 0, 5],
) == {
    "orders": [],
    "missed": 0,
    "closing": 3,
}, "a purchase already made holds the cover up before it lands"

assert build_replenishment_plan(
    {"held": 5, "floor": 5, "ceiling": 9, "pack": 1, "lead": 4, "inbound": []}, [0]
) == {
    "orders": [{"week": 1, "units": 4}],
    "missed": 0,
    "closing": 5,
}, "a purchase landing past the end of the run is still made"

assert build_replenishment_plan(
    {"held": 0, "floor": 0, "ceiling": 7, "pack": 3, "lead": 1, "inbound": []},
    [0, 0, 0],
) == {
    "orders": [{"week": 1, "units": 9}],
    "missed": 0,
    "closing": 9,
}, "a want of seven against a pack of three buys nine"

assert build_replenishment_plan(
    {"held": 3, "floor": 9, "ceiling": 9, "pack": 1, "lead": 1, "inbound": []}, []
) == {
    "orders": [],
    "missed": 0,
    "closing": 3,
}, "a run of no weeks buys nothing at all"

assert build_replenishment_plan(
    {"held": 5, "floor": 5, "ceiling": 5, "pack": 2, "lead": 1, "inbound": []}, [0]
) == {
    "orders": [],
    "missed": 0,
    "closing": 5,
}, "sitting on the floor with nothing wanted buys nothing"

assert build_replenishment_plan(
    {"held": 0, "floor": 0, "ceiling": 2, "pack": 1, "lead": 1, "inbound": []},
    [0, 3, 0, 0],
) == {
    "orders": [{"week": 1, "units": 2}, {"week": 2, "units": 2}],
    "missed": 1,
    "closing": 2,
}, "a run may buy more than once and still miss a draw"

SOUND = {"held": 1, "floor": 1, "ceiling": 2, "pack": 1, "lead": 1, "inbound": []}


def rejects(item, draws):
    try:
        build_replenishment_plan(item, draws)
    except ValueError:
        return True
    return False


assert rejects([1, 2], [0]), "an item that is not a mapping is rejected"
assert rejects(
    {"held": 1, "floor": 1, "ceiling": 2, "pack": 1}, [0]
), "an item missing keys is rejected"
assert rejects({**SOUND, "held": -1}, [0]), "a held below nought is rejected"
assert rejects(
    {**SOUND, "floor": 5, "ceiling": 4}, [0]
), "a ceiling below the floor is rejected"
assert rejects({**SOUND, "pack": 0}, [0]), "a pack below one is rejected"
assert rejects({**SOUND, "lead": 0}, [0]), "a lead below one is rejected"
assert rejects(
    {**SOUND, "inbound": "none"}, [0]
), "an inbound that is not a list is rejected"
assert rejects(
    {**SOUND, "inbound": [[2, 8]]}, [0]
), "an inbound entry that is not a mapping is rejected"
assert rejects(
    {**SOUND, "inbound": [{"week": 2}]}, [0]
), "an inbound entry missing its units is rejected"
assert rejects(
    {**SOUND, "inbound": [{"week": 0, "units": 8}]}, [0]
), "an inbound week below one is rejected"
assert rejects(
    {**SOUND, "inbound": [{"week": 3, "units": 8}, {"week": 3, "units": 1}]}, [0]
), "inbound weeks that do not climb are rejected"
assert rejects(SOUND, "0"), "a draws argument that is not a list is rejected"
assert rejects(SOUND, [-1]), "a draw below nought is rejected"
assert rejects(SOUND, [1.5]), "a draw that is not whole is rejected"
print("ok")
