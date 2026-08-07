from solution import cohort_hold_grid

MEMBERS = [["ana", 0], ["bo", 0], ["cy", 1]]
SIGHTINGS = [
    ["ana", 0],
    ["ana", 1],
    ["ana", 2],
    ["bo", 0],
    ["bo", 2],
    ["cy", 1],
    ["cy", 1],
    ["cy", 3],
]

assert cohort_hold_grid(MEMBERS, SIGHTINGS, 2) == [
    [0, 2, 2, 1, 2],
    [1, 1, 1, 0, 1],
], "two groups, horizon two, repeat sighting folded"

assert cohort_hold_grid(MEMBERS, SIGHTINGS, 0) == [
    [0, 2, 2],
    [1, 1, 1],
], "horizon zero leaves three entries per row"

assert cohort_hold_grid([["ana", 7]], [], 1) == [
    [7, 1, 0, 0]
], "no sightings gives a run of zeros"

assert cohort_hold_grid([], [], 3) == [], "nobody logged gives no rows"

assert cohort_hold_grid(
    [["zed", 5], ["ana", 2]],
    [["zed", 6], ["ana", 2]],
    1,
) == [
    [2, 1, 1, 0],
    [5, 1, 0, 1],
], "rows come back ordered by intake rising, not by logging order"

assert cohort_hold_grid(
    [["ana", 0], ["bo", 0], ["cy", 0]],
    [["ana", 4], ["bo", 4], ["cy", 4]],
    4,
) == [[0, 3, 0, 0, 0, 0, 3]], "a far offset is counted at exactly its own period"


def rejects(*args):
    try:
        cohort_hold_grid(*args)
    except ValueError:
        return True
    return False


assert rejects([["ana", 0], ["ana", 1]], [], 1), "a key logged twice is rejected"
assert rejects([["ana", 0]], [["bo", 0]], 1), "an unlogged key is rejected"
assert rejects([["ana", 4]], [["ana", 3]], 1), "a sighting before intake is rejected"
assert rejects([["ana", -1]], [], 1), "a negative period is rejected"
assert rejects([["ana", 1.5]], [], 1), "a fractional period is rejected"
assert rejects([["", 0]], [], 1), "an empty key is rejected"
assert rejects([["ana", 0]], [], 51), "a horizon past fifty is rejected"
assert rejects([["ana", 0]], [], -1), "a negative horizon is rejected"
assert rejects("ana", [], 1), "a non-list members argument is rejected"
assert rejects([["ana", 0, 9]], [], 1), "a record that is not a pair is rejected"
print("ok")
