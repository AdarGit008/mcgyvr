from solution import fit_budget


def rejects(prices, budget):
    try:
        fit_budget(prices, budget)
    except Exception:
        return True
    return False


assert fit_budget([3, 1, 2], 4) == 2, "the two cheapest fit"
assert fit_budget([5], 4) == 0, "nothing is affordable"
assert fit_budget([], 10) == 0, "nothing on offer"
assert fit_budget([1, 1, 1], 3) == 3, "everything fits exactly"
assert fit_budget([2, 2], 0) == 0, "no money to spend"
assert rejects([1], -1), "a negative budget is rejected"
print("ok")
