from solution import split_cargo

assert split_cargo([3, 1, 1, 2, 2, 1]) == [0, 3], (
    "even split, fewest items, then lexicographic"
)
assert split_cargo([5, 5, 4]) == [0], "fewer items preferred at equal difference"
assert split_cargo([7]) == [0], "single item stows forward"
assert split_cargo([2, 2]) == [0], "pair splits one each"
assert split_cargo([2, 2, 2, 2]) == [0, 1], (
    "lexicographic tie-break among equal-size stowages"
)
assert split_cargo([8, 3, 3, 4]) == [0], "heavy head sails alone"
assert split_cargo([10, 7, 5, 4]) == [0, 3], "closest achievable is two apart"


def rejects(weights):
    try:
        split_cargo(weights)
    except ValueError:
        return True
    return False


assert rejects([]), "empty manifest is rejected"
assert rejects([3, 0, 2]), "weight below one is rejected"
print("ok")
