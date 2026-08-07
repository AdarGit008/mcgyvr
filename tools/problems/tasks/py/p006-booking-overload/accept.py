from solution import first_overload

assert first_overload([[0, 10], [5, 15]], 1) == 5, "two overlapping, capacity one"
assert first_overload([[0, 10], [5, 15]], 2) == -1, "capacity two absorbs the pair"
assert first_overload([[0, 5], [5, 10]], 1) == -1, "touching spans never overlap"
assert first_overload([[0, 10], [2, 8], [4, 6]], 2) == 4, "third joiner overloads"
assert first_overload([[5, 15], [0, 10]], 1) == 5, "order of input is irrelevant"
assert first_overload([], 3) == -1, "no bookings never overload"
assert (
    first_overload([[0, 5], [3, 7], [5, 9]], 2) == -1
), "an end at time t frees the slot before a start at t takes it"


def rejects(*args):
    try:
        first_overload(*args)
    except ValueError:
        return True
    return False


assert rejects([[0, 5]], 0), "zero capacity is rejected"
assert rejects([[5, 5]], 1), "empty span is rejected"
assert rejects([[4, 2]], 1), "reversed span is rejected"
assert rejects([[0, 1.5]], 1), "fractional endpoint is rejected"
assert rejects("nope", 1), "non-list bookings are rejected"
print("ok")
