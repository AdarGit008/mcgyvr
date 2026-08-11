from solution import tally_column

assert tally_column([[1, 5], [2, 7], [3, 6]], 1) == {
    "count": 3,
    "total": 18,
    "low": 5,
    "high": 7,
}, "middle column of three rows"
assert tally_column([[0], [4]], 0) == {
    "count": 2,
    "total": 4,
    "low": 0,
    "high": 4,
}, "a zero cell still counts"
assert tally_column([[3], [5]], 0) == {
    "count": 2,
    "total": 8,
    "low": 3,
    "high": 5,
}, "low comes from the data"
assert tally_column([[-2], [-6]], 0) == {
    "count": 2,
    "total": -8,
    "low": -6,
    "high": -2,
}, "all-negative column"
assert tally_column([[9, 1]], 0) == {
    "count": 1,
    "total": 9,
    "low": 9,
    "high": 9,
}, "single row"


def rejects(*args):
    try:
        tally_column(*args)
    except Exception:
        return True
    return False


assert rejects([], 0), "empty table is rejected"
assert rejects([[1, 2], [3]], 0), "ragged rows are rejected"
assert rejects([[1, 2]], 2), "column outside the rows is rejected"
assert rejects([[1], ["7"]], 0), "non-number cell is rejected"
print("ok")
