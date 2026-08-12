from solution import owed_total


def rejects(entries):
    try:
        owed_total(entries)
    except Exception:
        return True
    return False


assert owed_total([10, 20]) == 30, "two charges add up"
assert owed_total([10, -4]) == 6, "a payment reduces the total"
assert owed_total([]) == 0, "an empty ledger"
assert owed_total([5, -5]) == 0, "paid off exactly"
assert owed_total([100, -30, -20]) == 50, "two payments against a charge"
assert rejects([-1]), "an overpaid ledger is rejected"
print("ok")
