from solution import raw_tally


def rejects(recipes, item, batches):
    try:
        raw_tally(recipes, item, batches)
    except ValueError:
        return True
    return False


assert raw_tally({}, "bolt", 1) == {"bolt": 1}, "an item without a recipe is raw"
assert raw_tally({"cart": ["wheel", "wheel", "frame"]}, "cart", 1) == {
    "wheel": 2,
    "frame": 1,
}, "repeated components add up"
SHOP = {
    "cart": ["wheel", "wheel", "frame"],
    "wheel": ["rim", "spoke", "spoke"],
}
assert raw_tally(SHOP, "cart", 1) == {
    "rim": 2,
    "spoke": 4,
    "frame": 1,
}, "nested recipes expand to raw parts"
assert raw_tally(SHOP, "cart", 3) == {
    "rim": 6,
    "spoke": 12,
    "frame": 3,
}, "batches scale the whole tally"
assert raw_tally({"kit": ["axle", "axle"], "axle": ["rod", "cap"]}, "kit", 1) == {
    "rod": 2,
    "cap": 2,
}, "a shared subassembly is charged once per use"
chain = {}
for level in range(1, 41):
    chain["p" + str(level)] = ["p" + str(level - 1), "p" + str(level - 1)]
assert raw_tally(chain, "p40", 1) == {
    "p0": 1099511627776
}, "a forty-level doubling chain resolves inside the time limit"
assert rejects({"a": ["a"]}, "a", 1), "a self-recipe is rejected"
assert rejects({"gear": ["hub"], "hub": ["gear"]}, "gear", 1), "a mutual cycle is rejected"
assert rejects({"a": []}, "a", 1), "an empty component list is rejected"
assert rejects({"a": [7]}, "a", 1), "a non-string component is rejected"
assert rejects({}, "", 1), "an empty item name is rejected"
assert rejects({}, 9, 1), "a non-string item is rejected"
assert rejects({}, "bolt", 0), "zero batches is rejected"
assert rejects({}, "bolt", 1.5), "fractional batches is rejected"
print("ok")
