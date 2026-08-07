from solution import bin_tallies

assert bin_tallies([1, 5, 7, 12], [0, 5, 10]) == {
    "bands": [1, 2],
    "below": 0,
    "above": 1,
}, "readings spread over bands and overflow"
assert bin_tallies([5], [0, 5, 10]) == {
    "bands": [0, 1],
    "below": 0,
    "above": 0,
}, "a reading on an inner edge lands in the upper band"
assert bin_tallies([0], [0, 5, 10]) == {
    "bands": [1, 0],
    "below": 0,
    "above": 0,
}, "a reading on the first edge is inside, not below"
assert bin_tallies([10], [0, 5, 10]) == {
    "bands": [0, 0],
    "below": 0,
    "above": 1,
}, "a reading on the last edge is above, not inside"
assert bin_tallies([-1, -50], [0, 5, 10]) == {
    "bands": [0, 0],
    "below": 2,
    "above": 0,
}, "readings under the first edge count as below"
assert bin_tallies([], [3, 9]) == {
    "bands": [0],
    "below": 0,
    "above": 0,
}, "no readings, all zero"
assert bin_tallies([-5, -2], [-10, -3, 0]) == {
    "bands": [1, 1],
    "below": 0,
    "above": 0,
}, "negative edges work like any others"


def rejects(readings, edges):
    try:
        bin_tallies(readings, edges)
    except ValueError:
        return True
    return False


assert rejects([1], [4]), "one edge is rejected"
assert rejects([1], [0, 5, 5]), "a repeated edge is rejected"
assert rejects([1], [5, 3]), "decreasing edges are rejected"
print("ok")
