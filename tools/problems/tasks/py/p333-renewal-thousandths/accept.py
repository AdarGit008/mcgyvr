from solution import renewal_thousandths

assert renewal_thousandths([["red", 8, [8, 6, 4, 1]]]) == [
    ["red", [1000, 750, 500, 125]]
], "every cycle is measured against the forming seats"

assert renewal_thousandths([["blue", 16, [1]]]) == [
    ["blue", [63]]
], "an exact half rounds upward"

assert renewal_thousandths([["gray", 3, [2, 1]]]) == [
    ["gray", [667, 333]]
], "thirds round to the nearest whole thousandth"

assert renewal_thousandths([["flat", 40, [40, 40, 40]]]) == [
    ["flat", [1000, 1000, 1000]]
], "a squad that keeps every seat reads full strength"

assert renewal_thousandths([["gone", 4, [2, 0, 0]]]) == [
    ["gone", [500, 0, 0]]
], "an empty cycle reads zero and does not poison the ones after it"

assert renewal_thousandths([["one", 5, []], ["two", 7, [7]]]) == [
    ["one", []],
    ["two", [1000]],
], "squads keep the order given and an empty run gives an empty strength list"

assert renewal_thousandths([]) == [], "no squads gives no rows"


def rejects(value):
    try:
        renewal_thousandths(value)
    except ValueError:
        return True
    return False


assert rejects([["red", 4, [1]], ["red", 4, [1]]]), "a repeated name is rejected"
assert rejects([["red", 4, [5]]]), "a tally above the forming seats is rejected"
assert rejects([["red", 4, [2, 3]]]), "a tally that climbs is rejected"
assert rejects([["red", 0, [0]]]), "zero forming seats is rejected"
assert rejects([["red", 4, [1.5]]]), "a fractional tally is rejected"
assert rejects([["", 4, [1]]]), "an empty squad name is rejected"
assert rejects([["red", 4]]), "a squad that is not a triple is rejected"
assert rejects("red"), "a non-list argument is rejected"
print("ok")
