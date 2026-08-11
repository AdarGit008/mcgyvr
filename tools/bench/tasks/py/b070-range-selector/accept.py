from solution import selector_hits

assert selector_hits([8, 12, 40, 41], "10-40") == 2, "one range"
assert selector_hits([3, 8, 22, 25], "1-5,20-30") == 3, "several terms"
assert selector_hits([15], "10-20,15") == 1, "overlapping terms count a value once"
assert selector_hits([10, 40], "10-40") == 2, "range ends are inclusive"
assert selector_hits([], "5") == 0, "no values"


def rejects(*args):
    try:
        selector_hits(*args)
    except ValueError:
        return True
    return False


assert rejects(["9"], "9"), "non-integer value is rejected"
assert rejects([1], ""), "empty selector is rejected"
assert rejects([1], "3,,9"), "empty term is rejected"
assert rejects([1], "9-4"), "reversed range is rejected"
print("ok")
