from solution import jar_balances

assert jar_balances(10, 100, [3, 4]) == [
    7,
    13,
], "monthly closes accumulate under a roomy lid"
assert jar_balances(10, 5, [0, 0]) == [5, 5], "the spill holds every close at the lid"
assert jar_balances(10, 6, [8]) == [2], "spill happens after paying, never before"
assert jar_balances(10, 100, [2, 17]) == [
    8,
    1,
], "last month's remainder helps cover a big outflow"
assert jar_balances(5, 10, [5]) == [0], "an exact payout closes at zero"
assert jar_balances(7, 3, []) == [], "no months, no closes"
assert jar_balances(0, 9, [0, 0, 0]) == [0, 0, 0], "a zero topup jar just stays empty"


def rejects(topup, lid, outflows):
    try:
        jar_balances(topup, lid, outflows)
    except ValueError:
        return True
    return False


assert rejects(10, 100, [15]), "an outflow the jar cannot cover is rejected"
assert rejects(10, 100, [-1]), "a negative outflow is rejected"
assert rejects(2.5, 100, [1]), "a fractional topup is rejected"
assert rejects(10, -3, [1]), "a negative lid is rejected"
assert rejects(10, 100, "3"), "a non-list outflows argument is rejected"
print("ok")
