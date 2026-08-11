from solution import split_cents

assert split_cents(100, [1, 1]) == [50, 50], "an even split leaves nothing over"
assert split_cents(101, [1, 1]) == [51, 50], "the odd cent goes to the earlier partner on a tie"
assert split_cents(100, [1, 1, 1]) == [34, 33, 33], "one cent over three equal partners lands first"
assert split_cents(5, [3, 1]) == [4, 1], "the larger weight takes the leftover cent"
assert split_cents(7, [1, 1, 1, 1]) == [2, 2, 2, 1], "three leftover cents fill the first three partners"
assert split_cents(0, [3, 1]) == [0, 0], "no takings share out as nothing each"
assert split_cents(99, [5]) == [99], "a lone partner takes the whole takings"


def rejects(total, weights):
    try:
        split_cents(total, weights)
    except ValueError:
        return True
    return False


assert rejects(10.5, [1, 1]), "a total that is not whole cents is rejected"
assert rejects(-5, [1, 1]), "a negative total is rejected"
assert rejects(10, "1,1"), "weights that are not a list are rejected"
assert rejects(10, []), "an empty weights list is rejected"
assert rejects(10, [1, 0]), "a weight that is not positive is rejected"
print("ok")
