from solution import combine_measures

assert combine_measures([], [1, 1]) == [], "no pours, no totals"
assert combine_measures([["milk", 2, 4]], [1, 1]) == [
    ["milk", 1, 2]
], "a single pour reduces to lowest terms"
assert combine_measures([["oil", 1, 3], ["oil", 1, 6]], [1, 1]) == [
    ["oil", 1, 2]
], "pours of one name total exactly"
assert combine_measures([["basil", 1, 2], ["anise", 1, 2]], [1, 1]) == [
    ["anise", 1, 2],
    ["basil", 1, 2],
], "names come back in ascending order"
assert combine_measures([["stock", 1, 2], ["stock", -1, 2]], [1, 1]) == [
    ["stock", 0, 1]
], "a cancelled total reads 0 over 1"
assert combine_measures([["flour", 1, 2]], [3, 2]) == [
    ["flour", 3, 4]
], "the batch factor scales the total"
assert combine_measures(
    [["rice", 1, 6], ["rice", 1, 6], ["salt", 1, 1]], [1, 2]
) == [["rice", 1, 6], ["salt", 1, 2]], "totals reduce again after scaling"


def rejects(pours, factor):
    try:
        combine_measures(pours, factor)
    except Exception:
        return True
    return False


assert rejects("milk", [1, 1]), "a non-list pour list"
assert rejects([["milk", 1]], [1, 1]), "a two-item entry is rejected"
assert rejects([["", 1, 2]], [1, 1]), "an empty name is rejected"
assert rejects([["milk", 1.5, 2]], [1, 1]), "a fractional numerator is rejected"
assert rejects([["milk", 1, 0]], [1, 1]), "a zero denominator is rejected"
assert rejects([["milk", 1, 2]], [1]), "a one-part factor is rejected"
assert rejects([["milk", 1, 2]], [0, 2]), "a non-positive factor part is rejected"
print("ok")
