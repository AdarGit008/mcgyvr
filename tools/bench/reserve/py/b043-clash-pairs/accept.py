from solution import clash_pairs

assert clash_pairs([]) == [], "no bookings means no clashes"
assert clash_pairs([[1, 3], [3, 5]]) == [], "touching bookings do not clash"
assert clash_pairs([[1, 4], [2, 6]]) == [[0, 1]], "overlapping bookings clash"
assert clash_pairs([[0, 10], [2, 4]]) == [[0, 1]], "a contained booking clashes"
assert clash_pairs([[1, 9], [2, 5], [6, 8]]) == [
    [0, 1],
    [0, 2],
], "clashes come ordered by first position then second"


def rejects(value):
    try:
        clash_pairs(value)
    except Exception:
        return True
    return False


assert rejects("busy"), "a non-list argument is rejected"
assert rejects([[1, 2, 3]]), "a three-item booking is rejected"
assert rejects([[1, 2.5]]), "a fractional bound is rejected"
assert rejects([[5, 5]]), "a booking of no length is rejected"
print("ok")
