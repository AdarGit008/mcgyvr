from solution import allocate_cents

assert allocate_cents(100, [1, 1, 1]) == [34, 33, 33], (
    "the odd cent goes to the earliest party on a remainder tie"
)
assert allocate_cents(101, [1, 1, 1]) == [34, 34, 33], (
    "two spare cents reach the two earliest parties"
)
assert allocate_cents(100, [1, 1, 3]) == [20, 20, 60], (
    "an exact division needs no correction"
)
assert allocate_cents(9, [3, 2, 2]) == [4, 3, 2], (
    "largest remainder first, then earliest on the tie"
)
assert allocate_cents(1, [10, 1]) == [1, 0], (
    "a single cent lands on the largest remainder"
)
assert allocate_cents(0, [2, 5]) == [0, 0], "nothing splits into nothings"
assert allocate_cents(7, [5]) == [7], "one party takes the whole sum"
assert sum(allocate_cents(997, [7, 11, 13])) == 997, "no cent appears or vanishes"


def rejects(total, weights):
    try:
        allocate_cents(total, weights)
    except ValueError:
        return True
    return False


assert rejects(10, []), "empty weights are rejected"
assert rejects(10, [1, 0]), "a zero weight is rejected"
assert rejects(-5, [1]), "a negative total is rejected"
assert rejects(10.5, [1]), "a fractional total is rejected"
assert rejects(10, [1.5, 2]), "a fractional weight is rejected"
print("ok")
