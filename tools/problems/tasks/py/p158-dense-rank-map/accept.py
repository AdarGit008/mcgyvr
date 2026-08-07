from solution import dense_rank_map

assert dense_rank_map([30, 10, 20], "asc") == [
    3,
    1,
    2,
], "ascending ranks land at original positions"
assert dense_rank_map([10, 20, 20, 30], "asc") == [
    1,
    2,
    2,
    3,
], "a tie never swallows the next rank"
assert dense_rank_map([10, 20, 20, 30], "desc") == [
    3,
    2,
    2,
    1,
], "descending flips the comparison, not the positions"
assert dense_rank_map([5, 1, 9], "desc") == [2, 3, 1], "descending with no ties"
assert dense_rank_map([7], "asc") == [1], "a single value ranks first"
assert dense_rank_map([4, 4, 4], "desc") == [1, 1, 1], "all equal values share rank one"
assert dense_rank_map([-5, 0, -5], "asc") == [1, 2, 1], "negative values rank fine"


def rejects(*args):
    try:
        dense_rank_map(*args)
    except ValueError:
        return True
    return False


assert rejects([], "asc"), "empty list is rejected"
assert rejects([1.5, 2], "asc"), "fractional value is rejected"
assert rejects([1, 2], "up"), "unknown order word is rejected"
print("ok")
