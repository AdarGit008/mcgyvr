from solution import climb_budget


def rejects(tolls):
    try:
        climb_budget(tolls)
    except Exception:
        return True
    return False


assert climb_budget(["10", "15", "20"]) == 15, "paying the middle rung alone wins"
assert climb_budget([]) == 0, "an empty board costs nothing"
assert climb_budget(["7"]) == 0, "a lone rung is skipped"
assert climb_budget(["1", "2"]) == 1, "the cheaper of the first two rungs is enough"
assert climb_budget(["1", "100", "1", "1", "1", "100", "1", "1", "100", "1"]) == 6, "a long board dodges the dear rungs"
assert climb_budget(["0", "0", "5"]) == 0, "free rungs leave the total at zero"
assert rejects(["3", "x"]), "a toll not written as digits is rejected"
assert rejects(["05"]), "a toll with a leading zero is rejected"
print("ok")
