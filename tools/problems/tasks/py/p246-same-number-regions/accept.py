from solution import label_value_regions

assert label_value_regions([[1]]) == {
    "map": [[1]],
    "sizes": [1],
    "values": [1],
}, "a single square"
assert label_value_regions([[1, 1], [1, 1]]) == {
    "map": [[1, 1], [1, 1]],
    "sizes": [4],
    "values": [1],
}, "one region filling the grid"
assert label_value_regions([[1, 2], [2, 1]]) == {
    "map": [[1, 2], [3, 4]],
    "sizes": [1, 1, 1, 1],
    "values": [1, 2, 2, 1],
}, "corner touching does not join squares"
assert label_value_regions([[7, 7, 7]]) == {
    "map": [[1, 1, 1]],
    "sizes": [3],
    "values": [7],
}, "one row is one region"
assert label_value_regions([[1], [2], [1]]) == {
    "map": [[1], [2], [3]],
    "sizes": [1, 1, 1],
    "values": [1, 2, 1],
}, "one column of three regions"
assert label_value_regions([[5, 5, 0], [0, 5, 0], [0, 0, 0]]) == {
    "map": [[1, 1, 2], [2, 1, 2], [2, 2, 2]],
    "sizes": [3, 6],
    "values": [5, 0],
}, "a region that wraps around another"
assert label_value_regions([[-3, -3], [4, -3]]) == {
    "map": [[1, 1], [2, 1]],
    "sizes": [3, 1],
    "values": [-3, 4],
}, "negative numbers join like any other"


def rejects(value):
    try:
        label_value_regions(value)
    except ValueError:
        return True
    return False


assert rejects(5), "a non-list grid is rejected"
assert rejects([]), "a grid with no rows is rejected"
assert rejects([[]]), "a row with no squares is rejected"
assert rejects(["ab"]), "a row that is not a list is rejected"
assert rejects([[1], [1, 2]]), "rows of unequal length are rejected"
assert rejects([[1, "a"]]), "a non-number square is rejected"
assert rejects([[1, 2.5]]), "a fractional square is rejected"
print("ok")
