from solution import name_step_distances

assert name_step_distances([[0, n] for n in range(12)]) == {
    "names": [
        "unison",
        "minor second",
        "major second",
        "minor third",
        "major third",
        "perfect fourth",
        "tritone",
        "perfect fifth",
        "minor sixth",
        "major sixth",
        "minor seventh",
        "major seventh",
    ],
    "lifts": [0] * 12,
    "colours": [
        "sweet",
        "sharp",
        "sharp",
        "sweet",
        "sweet",
        "sweet",
        "sharp",
        "sweet",
        "sweet",
        "sweet",
        "sharp",
        "sharp",
    ],
    "tally": {
        "unison": 1,
        "minor second": 1,
        "major second": 1,
        "minor third": 1,
        "major third": 1,
        "perfect fourth": 1,
        "tritone": 1,
        "perfect fifth": 1,
        "minor sixth": 1,
        "major sixth": 1,
        "minor seventh": 1,
        "major seventh": 1,
    },
    "widest": 11,
}, "every leftover of the table in turn"
assert name_step_distances(
    [[60, 60], [60, 61], [60, 67], [60, 72], [72, 60], [60, 84], [60, 79], [0, -5]]
) == {
    "names": [
        "unison",
        "minor second",
        "perfect fifth",
        "unison",
        "unison",
        "unison",
        "perfect fifth",
        "perfect fourth",
    ],
    "lifts": [0, 0, 0, 1, 1, 2, 1, 0],
    "colours": ["sweet", "sharp", "sweet", "sweet", "sweet", "sweet", "sweet", "sweet"],
    "tally": {
        "unison": 4,
        "minor second": 1,
        "perfect fifth": 2,
        "perfect fourth": 1,
    },
    "widest": 5,
}, "lifts count whole twelves and the order of the marks never matters"
assert name_step_distances([[0, 3], [10, 13]]) == {
    "names": ["minor third", "minor third"],
    "lifts": [0, 0],
    "colours": ["sweet", "sweet"],
    "tally": {"minor third": 2},
    "widest": 0,
}, "the earliest step takes a shared greatest reach"
assert name_step_distances([[-13, -1]]) == {
    "names": ["unison"],
    "lifts": [1],
    "colours": ["sweet"],
    "tally": {"unison": 1},
    "widest": 0,
}, "negative marks reach just the same"
assert name_step_distances([[0, 25]]) == {
    "names": ["minor second"],
    "lifts": [2],
    "colours": ["sharp"],
    "tally": {"minor second": 1},
    "widest": 0,
}, "two whole twelves and one over"


def rejects(value):
    try:
        name_step_distances(value)
    except ValueError:
        return True
    return False


assert rejects(7), "a non-list argument is rejected"
assert rejects([]), "an empty list of steps is rejected"
assert rejects([[60]]), "a step of one mark is rejected"
assert rejects([[60, 61, 62]]), "a step of three marks is rejected"
assert rejects(["ab"]), "a step that is not a list is rejected"
assert rejects([["60", 61]]), "a non-number mark is rejected"
assert rejects([[60, 61.5]]), "a fractional mark is rejected"
print("ok")
