from solution import cheapest_tray

items = [
    {"code": "sup", "price": 300},
    {"code": "mug", "price": 250},
    {"code": "pie", "price": 400},
]
bundles = [
    {"code": "deal", "price": 500, "holds": ["sup", "mug"]},
    {"code": "big", "price": 900, "holds": ["sup", "mug", "pie"]},
]


def rejects(sale, sets, needed):
    try:
        cheapest_tray(sale, sets, needed)
    except ValueError:
        return True
    return False


assert cheapest_tray(items, bundles, []) == {"total": 0, "picks": []}, (
    "requiring nothing costs nothing"
)
assert cheapest_tray(items, bundles, ["sup"]) == {
    "total": 300,
    "picks": ["sup"],
}, "a single item beats every bundle holding it"
assert cheapest_tray(items, bundles, ["sup", "mug"]) == {
    "total": 500,
    "picks": ["deal"],
}, "a bundle beats the two items it holds"
assert cheapest_tray(items, bundles, ["sup", "mug", "pie"]) == {
    "total": 900,
    "picks": ["big"],
}, "an equal price is settled by the smaller number of purchases"
assert cheapest_tray(items, bundles, ["mug"]) == {
    "total": 250,
    "picks": ["mug"],
}, "carrying more than was asked is allowed but never cheaper here"
assert cheapest_tray(
    [
        {"code": "a", "price": 100},
        {"code": "b", "price": 100},
        {"code": "c", "price": 100},
        {"code": "d", "price": 100},
    ],
    [{"code": "pack", "price": 250, "holds": ["a", "b", "c"]}],
    ["a", "b", "c", "d"],
) == {"total": 350, "picks": ["d", "pack"]}, (
    "a bundle and a loose item together beat four loose items"
)
assert cheapest_tray(
    [{"code": "x", "price": 100}],
    [
        {"code": "c2", "price": 100, "holds": ["x"]},
        {"code": "c1", "price": 100, "holds": ["x"]},
    ],
    ["x"],
) == {"total": 100, "picks": ["c1"]}, (
    "same price and same count is settled by the codes reading smaller"
)
assert cheapest_tray(items, bundles, ["pie", "sup"]) == {
    "total": 700,
    "picks": ["pie", "sup"],
}, "picks come back sorted upward whatever order they were found in"

assert rejects(items, bundles, ["soup"]), (
    "a required code no item sells is rejected"
)
assert rejects(items, bundles, ["sup", "sup"]), "a code required twice is rejected"
assert rejects(items, [{"code": "z", "price": 10, "holds": ["ghost"]}], ["sup"]), (
    "a bundle holding an unknown code is rejected"
)
assert rejects(items, [{"code": "z", "price": 10, "holds": []}], ["sup"]), (
    "a bundle holding nothing is rejected"
)
assert rejects(items, [{"code": "sup", "price": 10, "holds": ["sup"]}], ["sup"]), (
    "a bundle wearing an item's code is rejected"
)
assert rejects([{"code": "sup", "price": 0}], [], ["sup"]), (
    "a price below one penny is rejected"
)
assert rejects(
    [{"code": "i" + str(n), "price": 5} for n in range(15)], [], ["i0"]
), "fifteen things on sale is too many to search"
print("ok")
