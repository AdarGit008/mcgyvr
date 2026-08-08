from solution import plan_exhibit_tour

assert plan_exhibit_tour([], 100) == {
    "names": [],
    "worth": 0,
    "minutes": 0,
}, "a corridor with no stops plans nothing"

assert plan_exhibit_tour(
    [{"name": "Clocks", "walk": 2, "stay": 10, "worth": 5}], 0
) == {"names": [], "worth": 0, "minutes": 0}, "a budget of nought takes nothing in"

assert plan_exhibit_tour(
    [
        {"name": "Clocks", "walk": 2, "stay": 10, "worth": 5},
        {"name": "Maps", "walk": 3, "stay": 10, "worth": 6},
    ],
    15,
) == {
    "names": ["Maps"],
    "worth": 6,
    "minutes": 15,
}, "walking past a skipped stop is still paid for"

assert plan_exhibit_tour(
    [
        {"name": "Armour", "walk": 1, "stay": 100, "worth": 1},
        {"name": "Bells", "walk": 1, "stay": 2, "worth": 9},
    ],
    4,
) == {
    "names": ["Bells"],
    "worth": 9,
    "minutes": 4,
}, "a long stay early is skipped for a short one further along"

assert plan_exhibit_tour(
    [
        {"name": "Coins", "walk": 0, "stay": 5, "worth": 4},
        {"name": "Fans", "walk": 0, "stay": 4, "worth": 4},
    ],
    5,
) == {
    "names": ["Fans"],
    "worth": 4,
    "minutes": 4,
}, "equal worth is settled by the shorter visit"

assert plan_exhibit_tour(
    [
        {"name": "Kites", "walk": 0, "stay": 4, "worth": 6},
        {"name": "Lamps", "walk": 0, "stay": 2, "worth": 3},
        {"name": "Masks", "walk": 0, "stay": 2, "worth": 3},
    ],
    4,
) == {
    "names": ["Kites"],
    "worth": 6,
    "minutes": 4,
}, "equal worth and equal minutes are settled by the shorter list"

assert plan_exhibit_tour(
    [
        {"name": "Nets", "walk": 0, "stay": 3, "worth": 5},
        {"name": "Oars", "walk": 0, "stay": 3, "worth": 5},
    ],
    3,
) == {
    "names": ["Nets"],
    "worth": 5,
    "minutes": 3,
}, "a plan tied on every count keeps the earlier stop"

assert plan_exhibit_tour(
    [
        {"name": "Glass", "walk": 2, "stay": 8, "worth": 5},
        {"name": "Ivory", "walk": 1, "stay": 6, "worth": 4},
        {"name": "Prints", "walk": 4, "stay": 5, "worth": 7},
        {"name": "Silver", "walk": 1, "stay": 3, "worth": 2},
    ],
    20,
) == {
    "names": ["Glass", "Prints"],
    "worth": 12,
    "minutes": 20,
}, "a full corridor spends the budget to the minute"

assert plan_exhibit_tour(
    [{"name": "Tiles", "walk": 0, "stay": 7, "worth": 0}], 50
) == {"names": [], "worth": 0, "minutes": 0}, "a stop worth nothing is left out"


def rejects(stops, budget):
    try:
        plan_exhibit_tour(stops, budget)
    except ValueError:
        return True
    return False


assert rejects("Clocks", 10), "a stops argument that is not a list is rejected"
assert rejects([["Clocks", 1]], 10), "a stop that is not a mapping is rejected"
assert rejects(
    [{"name": "Clocks", "walk": 1, "stay": 2}], 10
), "a stop missing a key is rejected"
assert rejects(
    [{"name": "Clocks", "walk": 1, "stay": 2, "worth": 3, "floor": 1}], 10
), "a stop carrying a spare key is rejected"
assert rejects(
    [{"name": "", "walk": 1, "stay": 2, "worth": 3}], 10
), "an empty name is rejected"
assert rejects(
    [
        {"name": "Clocks", "walk": 1, "stay": 2, "worth": 3},
        {"name": "Clocks", "walk": 1, "stay": 2, "worth": 3},
    ],
    10,
), "a repeated name is rejected"
assert rejects(
    [{"name": "Clocks", "walk": -1, "stay": 2, "worth": 3}], 10
), "a walk below nought is rejected"
assert rejects(
    [{"name": "Clocks", "walk": 1, "stay": 0, "worth": 3}], 10
), "a stay below one is rejected"
assert rejects(
    [{"name": "Clocks", "walk": 1, "stay": 2, "worth": -3}], 10
), "a worth below nought is rejected"
assert rejects(
    [{"name": "Clocks", "walk": 1, "stay": 2.5, "worth": 3}], 10
), "a stay that is not whole is rejected"
assert rejects([], -1), "a budget below nought is rejected"
assert rejects([], 1.5), "a budget that is not whole is rejected"
print("ok")
