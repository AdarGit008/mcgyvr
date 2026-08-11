from solution import check_manifest

assert check_manifest({"sku": " ab-12 ", "count": 3, "note": "chipped"}) == {
    "sku": "AB-12",
    "count": 3,
    "note": "chipped",
}, "a full line files uppercased and trimmed"
assert check_manifest({"sku": "zz9", "count": 1}) == {
    "sku": "ZZ9",
    "count": 1,
    "note": "",
}, "an absent note files as the empty string"
assert check_manifest({"sku": "a1", "count": 5, "note": " as found "}) == {
    "sku": "A1",
    "count": 5,
    "note": " as found ",
}, "a note keeps the spaces it was given"
filed = {"sku": "q7", "count": 2}
check_manifest(filed)
assert filed == {"sku": "q7", "count": 2}, "the line handed in is untouched"


def rejects(line):
    try:
        check_manifest(line)
    except ValueError:
        return True
    return False


assert rejects({"sku": "a1", "count": 1, "colour": "red"}), "a fourth key is rejected"
assert rejects({"count": 1}), "a missing sku is rejected"
assert rejects({"sku": "   ", "count": 1}), "a blank sku is rejected"
assert rejects({"sku": "a1", "count": 0}), "a count of zero is rejected"
assert rejects({"sku": "a1", "count": 1, "note": 9}), "a note that is not a string is rejected"
print("ok")
