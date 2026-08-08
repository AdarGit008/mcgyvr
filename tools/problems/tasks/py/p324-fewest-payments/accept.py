from solution import fewest_payments

assert fewest_payments([]) == [], "no dues means no payments"
assert (
    fewest_payments([["ana", "bern", 10], ["bern", "ana", 10]]) == []
), "two people who owe each other the same net to nothing"
assert fewest_payments([["ana", "bern", 30], ["bern", "cid", 30]]) == [
    ["ana", "cid", 30]
], "the middle person drops out of the chain"
assert fewest_payments([["ana", "bern", 10], ["bern", "ana", 4]]) == [
    ["ana", "bern", 6]
], "opposing dues net before anything is drawn up"
assert fewest_payments(
    [["ana", "bern", 5], ["bern", "cid", 5], ["cid", "dov", 5]]
) == [["ana", "dov", 5]], "a three link chain collapses to one payment"
assert fewest_payments(
    [["ana", "cleo", 40], ["ana", "dov", 10], ["bern", "dov", 20]]
) == [
    ["ana", "cleo", 40],
    ["bern", "dov", 20],
    ["ana", "dov", 10],
], "deepest red against fullest black, twice, then an exact pair"
assert fewest_payments(
    [["ana", "dov", 30], ["ana", "edda", 30], ["bern", "cleo", 25]]
) == [
    ["bern", "cleo", 25],
    ["ana", "dov", 30],
    ["ana", "edda", 30],
], "the exact pair is paid off before the deeper position"
assert fewest_payments([["ana", "dov", 20], ["bran", "cleo", 20]]) == [
    ["ana", "cleo", 20],
    ["bran", "dov", 20],
], "among four exact pairs the first names decide"
assert fewest_payments([["ana", "bern", 30], ["ana", "cleo", 70]]) == [
    ["ana", "cleo", 70],
    ["ana", "bern", 30],
], "one red position pays the fullest black position first"


def rejects(value):
    try:
        fewest_payments(value)
    except ValueError:
        return True
    return False


assert rejects("dues"), "a non-list is rejected"
assert rejects([["ana", "bern"]]), "a due of two items is rejected"
assert rejects([["ana", "ana", 5]]), "one person on both sides is rejected"
assert rejects([["ana", "bern", 0]]), "an amount of zero is rejected"
assert rejects([["ana", "bern", 2.5]]), "a fractional amount is rejected"
assert rejects([["", "bern", 5]]), "an empty name is rejected"
assert rejects(
    [{"payer": "ana", "payee": "bern", "amount": 5}]
), "a due that is not a list is rejected"
print("ok")
