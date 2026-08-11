from solution import receipt_net

assert (
    receipt_net([{"amount": 10, "voided": False}, {"amount": 5, "voided": True}]) == 10
), "the voided line is left out"
assert (
    receipt_net([{"amount": 3, "voided": False}, {"amount": 4, "voided": False}]) == 7
), "nothing voided, everything counts"
assert receipt_net([{"amount": 9, "voided": True}]) == 0, "every line voided"
assert receipt_net([]) == 0, "an empty receipt"
assert receipt_net([{"amount": 0, "voided": False}]) == 0, "a zero line"
assert (
    receipt_net([{"amount": -2, "voided": False}, {"amount": 5, "voided": False}]) == 3
), "a refund line still counts"
print("ok")
