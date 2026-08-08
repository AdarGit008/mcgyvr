from solution import issue_cost_total


def arrive(units, cents):
    return {"kind": "in", "units": units, "cents": cents}


def leave(units):
    return {"kind": "out", "units": units}


assert issue_cost_total([]) == 0, "an empty log charges nothing"
assert issue_cost_total([arrive(2, 700)]) == 0, "arrivals alone charge nothing"
assert issue_cost_total([arrive(4, 25), leave(4)]) == 100, "one consignment out in one go"
assert (
    issue_cost_total([arrive(3, 10), leave(1), leave(1)]) == 20
), "two small issues off the same consignment"
assert (
    issue_cost_total([arrive(5, 10), arrive(5, 20), leave(7)]) == 90
), "the older consignment is priced first"
assert (
    issue_cost_total([arrive(5, 10), arrive(5, 20), leave(7), leave(3)]) == 150
), "what the first issue left behind prices the second"
assert (
    issue_cost_total([arrive(1, 1), arrive(1, 2), arrive(1, 4), leave(3)]) == 7
), "an issue spanning three consignments takes each at its own price"
assert (
    issue_cost_total([arrive(2, 50), leave(2), arrive(3, 10), leave(1)]) == 110
), "an emptied bin refills cleanly"


def rejects(moves):
    try:
        issue_cost_total(moves)
    except ValueError:
        return True
    return False


assert rejects([leave(1)]), "issuing from an empty bin is rejected"
assert rejects([arrive(2, 5), leave(3)]), "issuing more than the bin holds is rejected"
assert rejects([{"kind": "scrap", "units": 1}]), "an unknown kind is rejected"
assert rejects([arrive(0, 5)]), "an arrival of no parts is rejected"
assert rejects([arrive(1.5, 5)]), "a fractional unit count is rejected"
assert rejects([{"kind": "in", "units": 2}]), "an unpriced arrival is rejected"
assert rejects([arrive(1, -5)]), "a negative price is rejected"
assert rejects(
    [arrive(2, 5), {"kind": "out", "units": 1, "cents": 9}]
), "a priced issue is rejected"
assert rejects("in"), "a string argument is rejected"
print("ok")
