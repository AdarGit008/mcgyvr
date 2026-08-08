from solution import cost_basis_report

assert cost_basis_report([]) == {
    "fifoSold": 0,
    "averageSold": 0,
    "unitsLeft": 0,
    "fifoValue": 0,
    "averageValue": 0,
}, "an empty stream costs nothing"
assert cost_basis_report([["buy", 10, 100], ["buy", 10, 200]]) == {
    "fifoSold": 0,
    "averageSold": 0,
    "unitsLeft": 20,
    "fifoValue": 3000,
    "averageValue": 3000,
}, "receipts alone leave both methods carrying the same value"
assert cost_basis_report([["buy", 5, 7], ["sell", 5]]) == {
    "fifoSold": 35,
    "averageSold": 35,
    "unitsLeft": 0,
    "fifoValue": 0,
    "averageValue": 0,
}, "clearing one layer empties the stock"
assert cost_basis_report(
    [
        ["buy", 10, 100],
        ["buy", 10, 200],
        ["sell", 15],
        ["buy", 5, 300],
        ["sell", 6],
    ]
) == {
    "fifoSold": 3300,
    "averageSold": 3600,
    "unitsLeft": 4,
    "fifoValue": 1200,
    "averageValue": 900,
}, "a despatch eating two layers parts the two methods"
assert cost_basis_report(
    [["buy", 2, 101], ["buy", 1, 100], ["sell", 1], ["sell", 1]]
) == {
    "fifoSold": 202,
    "averageSold": 201,
    "unitsLeft": 1,
    "fifoValue": 100,
    "averageValue": 101,
}, "the dropped fraction stays with the pool"
assert cost_basis_report(
    [["buy", 2, 50], ["sell", 2], ["buy", 3, 10], ["sell", 1]]
) == {
    "fifoSold": 110,
    "averageSold": 110,
    "unitsLeft": 2,
    "fifoValue": 20,
    "averageValue": 20,
}, "restocking from empty starts the pool over"
assert cost_basis_report([["buy", 2, 0], ["sell", 1]]) == {
    "fifoSold": 0,
    "averageSold": 0,
    "unitsLeft": 1,
    "fifoValue": 0,
    "averageValue": 0,
}, "free goods cost nothing to despatch"

whole = cost_basis_report(
    [
        ["buy", 7, 13],
        ["buy", 3, 29],
        ["sell", 4],
        ["buy", 6, 5],
        ["sell", 9],
    ]
)
spend = 7 * 13 + 3 * 29 + 6 * 5
assert whole["fifoSold"] + whole["fifoValue"] == spend, "fifo splits the purchase cost"
assert (
    whole["averageSold"] + whole["averageValue"] == spend
), "the average method splits the same purchase cost"
assert whole["unitsLeft"] == 3, "the units left agree with the events"


def rejects(events):
    try:
        cost_basis_report(events)
    except ValueError:
        return True
    return False


assert rejects([["sell", 1]]), "despatching from nothing is rejected"
assert rejects([["buy", 2, 5], ["sell", 3]]), "an oversized despatch is rejected"
assert rejects([["scrap", 1]]), "an unknown event is rejected"
assert rejects([["buy", 2]]), "a receipt without a price is rejected"
assert rejects([["buy", 2, 5], ["sell", 1, 5]]), "a three-entry despatch is rejected"
assert rejects([["buy", 0, 5]]), "a receipt of no units is rejected"
assert rejects([["buy", 1.5, 5]]), "a fractional unit count is rejected"
assert rejects([["buy", 1, -5]]), "a negative unit price is rejected"
assert rejects("buy"), "a string argument is rejected"
print("ok")
