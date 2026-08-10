from solution import pick_harvest_lots

assert pick_harvest_lots([["kale", 5, 40, 10]], 10, 99, 1) == {
    "picks": [["kale", 10]],
    "cost": 400,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [],
}, "single lot exact fill"
assert pick_harvest_lots(
    [["beet", 9, 50, 4], ["arugula", 3, 50, 4], ["corn", 6, 50, 4]], 10, 99, 1
) == {
    "picks": [["arugula", 4], ["corn", 4], ["beet", 2]],
    "cost": 500,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [["beet", 2]],
}, "unsorted lots are taken earliest expiry first"
assert pick_harvest_lots([["plum", 4, 30, 5], ["pear", 4, 20, 5]], 6, 99, 0) == {
    "picks": [["pear", 5], ["plum", 1]],
    "cost": 130,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [["plum", 4]],
}, "expiry tie broken by lower unit cost"
assert pick_harvest_lots([["fig", 4, 20, 3], ["date", 4, 20, 3]], 4, 99, 0) == {
    "picks": [["date", 3], ["fig", 1]],
    "cost": 80,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [["fig", 2]],
}, "expiry and cost tie broken by name"
assert pick_harvest_lots([["oat", 7, 10, 50]], 20, 99, 1) == {
    "picks": [["oat", 20]],
    "cost": 200,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [["oat", 30]],
}, "partial take leaves the rest as leftover"
assert pick_harvest_lots(
    [["rye", 2, 10, 5], ["soy", 5, 10, 5], ["ulu", 9, 90, 2]], 5, 99, 2
) == {
    "picks": [["soy", 5]],
    "cost": 50,
    "shortfall": 0,
    "skipped": ["rye"],
    "leftovers": [["ulu", 2]],
}, "a lot expiring today is skipped and untouched stock is leftover"
assert pick_harvest_lots([["yam", 9, 25, 3]], 8, 99, 0) == {
    "picks": [["yam", 3]],
    "cost": 75,
    "shortfall": 5,
    "skipped": [],
    "leftovers": [],
}, "insufficient stock reports the shortfall"
assert pick_harvest_lots([], 4, 9, 0) == {
    "picks": [],
    "cost": 0,
    "shortfall": 4,
    "skipped": [],
    "leftovers": [],
}, "no lots at all"
assert pick_harvest_lots([["mint", 5, 10, 9], ["sage", 6, 10, 9]], 6, 3, 0) == {
    "picks": [["mint", 3], ["sage", 3]],
    "cost": 60,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [["mint", 6], ["sage", 6]],
}, "the cap spreads the order across lots"
assert pick_harvest_lots([["leek", 8, 12, 100]], 10, 4, 0) == {
    "picks": [["leek", 4]],
    "cost": 48,
    "shortfall": 6,
    "skipped": [],
    "leftovers": [["leek", 96]],
}, "the cap can leave a shortfall despite ample stock"
assert pick_harvest_lots([["bean", 3, 15, 2], ["chard", 4, 22, 3]], 5, 99, 1) == {
    "picks": [["bean", 2], ["chard", 3]],
    "cost": 96,
    "shortfall": 0,
    "skipped": [],
    "leftovers": [],
}, "costs add up across drained lots"
assert pick_harvest_lots([["okra", 1, 5, 5], ["kohlrabi", 0, 5, 5]], 2, 99, 3) == {
    "picks": [],
    "cost": 0,
    "shortfall": 2,
    "skipped": ["okra", "kohlrabi"],
    "leftovers": [],
}, "all lots expired"


def rejects(*args):
    try:
        pick_harvest_lots(*args)
    except ValueError:
        return True
    return False


assert rejects([["ash", 2, 3]], 1, 1, 0), "lot is not a quadruple"
assert rejects([["", 5, 3, 2]], 1, 1, 0), "empty lot name"
assert rejects([["dill", 5, 3, 2], ["dill", 6, 4, 1]], 1, 1, 0), "repeated lot name"
assert rejects([["dill", 5.5, 3, 2]], 1, 1, 0), "fractional expiry day"
assert rejects([["dill", 5, -3, 2]], 1, 1, 0), "negative unit cost"
assert rejects([["dill", 5, 3, 0]], 1, 1, 0), "zero lot quantity"
assert rejects([], 0, 1, 0), "zero order quantity"
assert rejects([], 1, 0, 0), "zero per-lot cap"
assert rejects([], 1, 1, 0.5), "fractional current day"
print("ok")
