from solution import mend_shards

assert mend_shards([[1, 2], [1, 2], [3, 2]]) == [
    1,
    2,
], "the most-held value wins each position"
assert mend_shards([[None, 5], [7, None], [7, 5]]) == [
    7,
    5,
], "corrupted slots simply drop out of the count"
assert mend_shards([[None, 1], [None, 1], [4, None]]) == [
    4,
    1,
], "corruption is never a candidate, even when it is the most common state"
assert mend_shards([[2], [9], [9], [2]]) == [
    2
], "a count tie goes to the value held by the earliest copy"
assert mend_shards([[9], [2], [2], [9]]) == [
    9
], "the earliest-copy rule is about position in the list, not value size"
assert mend_shards([[None], [None]]) == [-1], "a position corrupted everywhere mends to -1"
assert mend_shards([[5, None, 3]]) == [
    5,
    -1,
    3,
], "a single copy mends to itself with -1 in its holes"
assert mend_shards([[], []]) == [], "empty copies mend to an empty array"


def rejects(copies):
    try:
        mend_shards(copies)
    except ValueError:
        return True
    return False


assert rejects([[1, 2], [1]]), "copies of different lengths are rejected"
assert rejects([[-3]]), "a negative slot is rejected"
assert rejects([["a"]]), "a string slot is rejected"
assert rejects([]), "an empty list of copies is rejected"
print("ok")
