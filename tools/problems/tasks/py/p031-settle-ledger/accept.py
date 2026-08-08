from solution import settle_ledger

assert settle_ledger(
    [
        {"account": "x", "amount": -5, "seq": 2},
        {"account": "x", "amount": 10, "seq": 1},
    ]
) == [["x", 5]], "entries replay in seq order, not list order"
assert settle_ledger(
    [
        {"account": "b", "amount": 7, "seq": 10},
        {"account": "a", "amount": 3, "seq": 20},
        {"account": "c", "amount": 1, "seq": 30},
    ]
) == [["a", 3], ["b", 7], ["c", 1]], "output sorts by account name, seq gaps allowed"
assert settle_ledger(
    [
        {"account": "x", "amount": 5, "seq": 1},
        {"account": "x", "amount": -5, "seq": 2},
        {"account": "y", "amount": 2, "seq": 3},
    ]
) == [["y", 2]], "an account settling to zero is omitted"
assert settle_ledger(
    [
        {"account": "a", "amount": 10, "seq": 1},
        {"account": "b", "amount": 4, "seq": 2},
        {"account": "a", "amount": -3, "seq": 3},
        {"account": "b", "amount": -4, "seq": 4},
    ]
) == [["a", 7]], "interleaved accounts settle independently"
assert settle_ledger([]) == [], "empty ledger settles empty"


def rejects(entries):
    try:
        settle_ledger(entries)
    except ValueError:
        return True
    return False


assert rejects(
    [
        {"account": "x", "amount": 5, "seq": 1},
        {"account": "x", "amount": -6, "seq": 2},
    ]
), "overdraft is rejected"
assert rejects(
    [
        {"account": "x", "amount": 5, "seq": 1},
        {"account": "x", "amount": -6, "seq": 2},
        {"account": "x", "amount": 10, "seq": 3},
    ]
), "mid-replay overdraft is rejected despite later deposit"
assert rejects(
    [
        {"account": "x", "amount": 1, "seq": 1},
        {"account": "y", "amount": 1, "seq": 1},
    ]
), "duplicate seq is rejected"
assert rejects([{"account": "x", "seq": 1}]), "missing amount is rejected"
assert rejects([{"account": "", "amount": 1, "seq": 1}]), "empty account name is rejected"
assert rejects([{"account": "x", "amount": 1.5, "seq": 1}]), "fractional amount is rejected"
assert rejects([{"account": 9, "amount": 1, "seq": 1}]), "non-string account is rejected"
print("ok")
