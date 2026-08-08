from solution import carve_set

assert carve_set([]) == [], "no instructions"
assert carve_set([["add", 2, 6]]) == [[2, 6]], "a single add"
assert carve_set([["add", 0, 3], ["add", 3, 5]]) == [[0, 5]], "touching adds fuse"
assert carve_set([["add", 0, 4], ["add", 8, 12], ["add", 2, 9]]) == [
    [0, 12]
], "an add can weld separate pieces"
assert carve_set([["add", 0, 10], ["cut", 3, 6]]) == [
    [0, 3],
    [6, 10],
], "a cut through the middle leaves two pieces"
assert carve_set([["add", 0, 10], ["cut", 3, 6], ["add", 3, 6]]) == [
    [0, 10]
], "re-adding the cut welds the stretch back"
assert carve_set([["add", 2, 5], ["cut", 0, 9]]) == [], "cutting everything empties the set"
assert carve_set([["add", 2, 5], ["cut", 5, 9], ["cut", 0, 2]]) == [
    [2, 5]
], "cuts outside the held range change nothing"
assert carve_set([["cut", 1, 3], ["add", 4, 6]]) == [
    [4, 6]
], "cutting from the empty set is allowed"


def rejects(steps):
    try:
        carve_set(steps)
    except ValueError:
        return True
    return False


assert rejects([["del", 0, 2]]), "unknown verb is rejected"
assert rejects([["add", 0, 0]]), "an empty range is rejected"
assert rejects([["add", 4, 1]]), "a backwards range is rejected"
assert rejects([["cut", 0, 2.5]]), "a fractional bound is rejected"
print("ok")
