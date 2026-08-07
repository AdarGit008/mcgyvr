from solution import first_rotation_breach

PERMITS = [
    ["wheat", "barley"],
    ["wheat", "clover"],
    ["barley", "clover"],
    ["barley", "wheat"],
    ["clover", "wheat"],
    ["clover", "barley"],
    ["clover", "beet"],
    ["beet", "wheat"],
]


def rejects(log, permits):
    try:
        first_rotation_breach(log, permits)
    except ValueError:
        return True
    return False


assert (
    first_rotation_breach([["wheat", "barley", "clover", "wheat"]], PERMITS) == "clear"
), "a four-season cycle offends nothing"
assert (
    first_rotation_breach([["wheat"], ["beet"]], PERMITS) == "clear"
), "a single season has nothing behind it to judge"
assert (
    first_rotation_breach([["wheat", "beet"]], PERMITS) == "plot 1 season 2"
), "the table refuses beet behind wheat"
assert (
    first_rotation_breach([["wheat", "barley", "wheat"]], PERMITS) == "plot 1 season 3"
), "wheat returns with only one season between"
assert (
    first_rotation_breach([["wheat", "barley", "clover", "barley"]], PERMITS)
    == "plot 1 season 4"
), "barley returns with two seasons between"
assert (
    first_rotation_breach(
        [
            ["wheat", "barley", "clover", "clover"],
            ["barley", "barley", "wheat", "clover"],
        ],
        PERMITS,
    )
    == "plot 2 season 2"
), "the early breach on the second plot outranks the late one on the first"
assert (
    first_rotation_breach(
        [
            ["wheat", "clover", "wheat"],
            ["barley", "clover", "barley"],
        ],
        PERMITS,
    )
    == "plot 1 season 3"
), "when a season holds two breaches the lower plot is named"

assert rejects([], PERMITS), "an empty record is rejected"
assert rejects("wheat", PERMITS), "a record that is not a list is rejected"
assert rejects([[]], PERMITS), "a plot row with no seasons is rejected"
assert rejects(
    [["wheat", "barley"], ["wheat"]], PERMITS
), "rows of unequal length are rejected"
assert rejects([["wheat", ""]], PERMITS), "a blank crop name is rejected"
assert rejects([["wheat", "barley"]], "wheat"), "a table that is not a list is rejected"
assert rejects(
    [["wheat", "barley"]], [["wheat"]]
), "a table row that is not a pair is rejected"
print("ok")
