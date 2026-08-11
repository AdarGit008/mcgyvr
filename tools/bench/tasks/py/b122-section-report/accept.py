from solution import section_report

woven = [["fruit", "apple", 3], ["dairy", "milk", 2], ["fruit", "pear", 4]]
assert section_report(woven) == {
    "lines": [
        ["item", "fruit", "apple", 3],
        ["item", "fruit", "pear", 4],
        ["section", "fruit", "", 7],
        ["item", "dairy", "milk", 2],
        ["section", "dairy", "", 2],
        ["grand", "", "", 9],
    ],
    "sections": [["fruit", 2, 7], ["dairy", 1, 2]],
    "grand": 9,
}, "an interrupted section regroups under its first appearance"
assert section_report([["ads", "spot", 5], ["web", "banner", 2]]) == {
    "lines": [
        ["item", "ads", "spot", 5],
        ["section", "ads", "", 5],
        ["item", "web", "banner", 2],
        ["section", "web", "", 2],
        ["grand", "", "", 7],
    ],
    "sections": [["ads", 1, 5], ["web", 1, 2]],
    "grand": 7,
}, "each section carries its own subtotal"
assert section_report([["ops", "toner", -4]]) == {
    "lines": [
        ["item", "ops", "toner", -4],
        ["section", "ops", "", -4],
        ["grand", "", "", -4],
    ],
    "sections": [["ops", 1, -4]],
    "grand": -4,
}, "a lone negative row flows through"
assert section_report([]) == {
    "lines": [["grand", "", "", 0]],
    "sections": [],
    "grand": 0,
}, "no rows still yields the grand line"
tied = [["beta", "x", 4], ["alpha", "y", 4]]
assert section_report(tied)["lines"] == [
    ["item", "beta", "x", 4],
    ["section", "beta", "", 4],
    ["item", "alpha", "y", 4],
    ["section", "alpha", "", 4],
    ["grand", "", "", 8],
], "lines keep first-appearance order"
assert section_report(tied)["sections"] == [
    ["alpha", 1, 4],
    ["beta", 1, 4],
], "tied subtotals rank by name"
assert section_report([["s1", "a", 1], ["s2", "b", 9], ["s3", "c", 5]])["sections"] == [
    ["s2", 1, 9],
    ["s3", 1, 5],
    ["s1", 1, 1],
], "summary ranks by subtotal descending"
assert section_report([["kit", "bolt", 0], ["kit", "bolt", 2]]) == {
    "lines": [
        ["item", "kit", "bolt", 0],
        ["item", "kit", "bolt", 2],
        ["section", "kit", "", 2],
        ["grand", "", "", 2],
    ],
    "sections": [["kit", 2, 2]],
    "grand": 2,
}, "repeated labels and a zero amount are fine"
assert section_report([["a", "x", 1], ["b", "y", 1], ["a", "z", 1], ["b", "w", 1]]) == {
    "lines": [
        ["item", "a", "x", 1],
        ["item", "a", "z", 1],
        ["section", "a", "", 2],
        ["item", "b", "y", 1],
        ["item", "b", "w", 1],
        ["section", "b", "", 2],
        ["grand", "", "", 4],
    ],
    "sections": [["a", 2, 2], ["b", 2, 2]],
    "grand": 4,
}, "two sections woven twice regroup cleanly"


def rejects(value):
    try:
        section_report(value)
    except ValueError:
        return True
    return False


assert rejects("rows"), "non-list rows"
assert rejects([["a", "b"]]), "two-item row"
assert rejects([["a", "b", 1, 2]]), "four-item row"
assert rejects([["", "b", 1]]), "empty section name"
assert rejects([[7, "b", 1]]), "non-string section"
assert rejects([["a", 42, 1]]), "non-string label"
assert rejects([["a", "b", "9"]]), "string amount"
print("ok")
