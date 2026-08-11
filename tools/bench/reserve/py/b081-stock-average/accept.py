from solution import receipt_cents, run_stockbook

assert run_stockbook([]) == {"held": 0, "worth": 0, "issued": 0}, "empty book"
assert run_stockbook([["receive", 10, 100]]) == {
    "held": 10,
    "worth": 1000,
    "issued": 0,
}, "one receive stocks the book"
assert run_stockbook([["receive", 10, 100], ["receive", 10, 200], ["issue", 5]]) == {
    "held": 15,
    "worth": 2250,
    "issued": 750,
}, "an issue relieves the moving average, not the latest price"
assert run_stockbook([["receive", 1, 50], ["receive", 2, 25], ["issue", 1]]) == {
    "held": 2,
    "worth": 67,
    "issued": 33,
}, "an uneven relief floors to whole cents"
assert run_stockbook(
    [["receive", 1, 50], ["receive", 2, 25], ["issue", 1], ["issue", 2]]
) == {
    "held": 0,
    "worth": 0,
    "issued": 100,
}, "issuing everything empties the book exactly"
assert receipt_cents(3, 250) == 750, "a receipt costs quantity times unit cost"


def rejects(moves):
    try:
        run_stockbook(moves)
    except ValueError:
        return True
    return False


assert rejects(
    [["receive", 2, 10], ["issue", 3]]
), "issuing more than is held is rejected"
assert rejects([["receive", 2, 10], ["issue", 0]]), "a zero issue is rejected"
assert rejects([["receive", 4, 10], ["issue", 1.5]]), "a fractional issue is rejected"
assert rejects([["receive", 0, 10]]), "a zero receive is rejected"
assert rejects([["receive", 2, -5]]), "a negative unit cost is rejected"


def helper_rejects(qty, unit_cents):
    try:
        receipt_cents(qty, unit_cents)
    except ValueError:
        return True
    return False


assert helper_rejects(1.5, 10), "a fractional receive is rejected"
print("ok")
