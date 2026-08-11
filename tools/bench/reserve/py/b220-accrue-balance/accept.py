from solution import accrue_balance

assert accrue_balance(100000, 250, 1) == 102500, "a period paying whole cents credits them all"
assert accrue_balance(1, 1, 1) == 1, "interest far under a cent leaves the balance alone"
assert accrue_balance(100, 50, 1) == 100, "exactly half a cent stays put on an even balance"
assert accrue_balance(25, 200, 1) == 26, "exactly half a cent buys a cent on an odd balance"
assert accrue_balance(1000, 125, 3) == 1038, "carried remainders compound and finally buy a cent"
assert accrue_balance(4321, 375, 0) == 4321, "no periods leaves the opening balance untouched"


def rejects(*args):
    try:
        accrue_balance(*args)
    except Exception:
        return True
    return False


assert rejects(1000, 250, -1), "a negative period count is rejected"
assert rejects(1000, -250, 2), "a negative rate is rejected"
print("ok")
