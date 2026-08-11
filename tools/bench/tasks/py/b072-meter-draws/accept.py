from solution import meter_draws, remaining_for

assert meter_draws([], 10) == {"used": {}, "denied": []}, "no draws"
assert meter_draws([["a", 6], ["a", 5]], 10) == {
    "used": {"a": 6},
    "denied": [1],
}, "a draw past the allowance is refused"
assert meter_draws([["a", 6], ["b", 8], ["a", 4]], 10) == {
    "used": {"a": 10, "b": 8},
    "denied": [],
}, "keys meter separately and an exact fill is allowed"
assert meter_draws([["a", 11], ["a", 2]], 10) == {
    "used": {"a": 2},
    "denied": [0],
}, "a refused draw leaves later draws unharmed"
assert meter_draws([["z", 11]], 10) == {
    "used": {"z": 0},
    "denied": [0],
}, "a fully refused key still enters the ledger at zero"
assert remaining_for({}, "a", 10) == 10, "unseen key has the full allowance"
assert remaining_for({"a": 3}, "a", 10) == 7, "helper subtracts recorded spend"


def rejects(*args):
    try:
        meter_draws(*args)
    except ValueError:
        return True
    return False


assert rejects([], 0), "zero allowance is rejected"
assert rejects([["", 1]], 10), "empty key is rejected"
assert rejects([["a", 0]], 10), "zero units is rejected"
assert rejects([["a", 1.5]], 10), "fractional units is rejected"
print("ok")
