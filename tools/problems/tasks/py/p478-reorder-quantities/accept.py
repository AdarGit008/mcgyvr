from solution import reorder_quantities

assert reorder_quantities(
    [{"sku": "BOLT", "shelf": 2, "due": 0, "low": 5, "high": 20, "pack": 6}]
) == [{"sku": "BOLT", "units": 18}], "a want of eighteen against a pack of six buys three packs"

assert (
    reorder_quantities(
        [{"sku": "BOLT", "shelf": 9, "due": 0, "low": 5, "high": 20, "pack": 6}]
    )
    == []
), "a shelf above the low buys nothing"

assert reorder_quantities(
    [{"sku": "NUT", "shelf": 5, "due": 0, "low": 5, "high": 12, "pack": 1}]
) == [{"sku": "NUT", "units": 7}], "sitting exactly on the low trips the buy"

assert (
    reorder_quantities(
        [{"sku": "NUT", "shelf": 1, "due": 9, "low": 5, "high": 20, "pack": 1}]
    )
    == []
), "units already bought hold the cover above the low"

assert reorder_quantities(
    [{"sku": "WASHER", "shelf": 0, "due": 0, "low": 0, "high": 10, "pack": 4}]
) == [{"sku": "WASHER", "units": 12}], "a want of ten against a pack of four buys twelve"

assert (
    reorder_quantities(
        [{"sku": "SHIM", "shelf": 5, "due": 0, "low": 5, "high": 5, "pack": 3}]
    )
    == []
), "a want of nought buys nothing even on the low"

assert reorder_quantities(
    [
        {"sku": "BOLT", "shelf": 2, "due": 0, "low": 5, "high": 20, "pack": 6},
        {"sku": "NUT", "shelf": 40, "due": 0, "low": 5, "high": 20, "pack": 6},
        {"sku": "SHIM", "shelf": 0, "due": 1, "low": 3, "high": 9, "pack": 2},
    ]
) == [
    {"sku": "BOLT", "units": 18},
    {"sku": "SHIM", "units": 8},
], "only the lines that trip appear, in the order given"

assert reorder_quantities([]) == [], "an empty storeroom buys nothing"


def rejects(lines):
    try:
        reorder_quantities(lines)
    except ValueError:
        return True
    return False


assert rejects("BOLT"), "a lines argument that is not a list is rejected"
assert rejects([["BOLT", 1]]), "a line that is not a mapping is rejected"
assert rejects(
    [{"sku": "BOLT", "shelf": 1, "due": 0, "low": 1, "high": 2}]
), "a line missing its pack is rejected"
assert rejects(
    [{"sku": "BOLT", "shelf": 1, "due": 0, "low": 1, "high": 2, "pack": 1, "bin": "A"}]
), "a line carrying a spare key is rejected"
assert rejects(
    [{"sku": "", "shelf": 1, "due": 0, "low": 1, "high": 2, "pack": 1}]
), "an empty sku is rejected"
assert rejects(
    [
        {"sku": "BOLT", "shelf": 1, "due": 0, "low": 1, "high": 2, "pack": 1},
        {"sku": "BOLT", "shelf": 1, "due": 0, "low": 1, "high": 2, "pack": 1},
    ]
), "a repeated sku is rejected"
assert rejects(
    [{"sku": "BOLT", "shelf": -1, "due": 0, "low": 1, "high": 2, "pack": 1}]
), "a shelf below nought is rejected"
assert rejects(
    [{"sku": "BOLT", "shelf": 1, "due": 0, "low": 5, "high": 4, "pack": 1}]
), "a high below the low is rejected"
assert rejects(
    [{"sku": "BOLT", "shelf": 1, "due": 0, "low": 1, "high": 2, "pack": 0}]
), "a pack below one is rejected"
assert rejects(
    [{"sku": "BOLT", "shelf": 1.5, "due": 0, "low": 1, "high": 2, "pack": 1}]
), "a shelf that is not whole is rejected"
print("ok")
