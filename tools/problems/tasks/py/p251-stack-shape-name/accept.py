from solution import name_triad_stack

assert name_triad_stack([0, 4, 7]) == {"base": 0, "name": "major"}, "the plainest shape"
assert name_triad_stack([60, 64, 67, 72, 76]) == {
    "base": 0,
    "name": "major",
}, "repeats and higher octaves fold away"
assert name_triad_stack([-12, -8, -5]) == {
    "base": 0,
    "name": "major",
}, "negative marks fold up into range"
assert name_triad_stack([4, 7, 11]) == {"base": 4, "name": "minor"}, "a base away from zero"
assert name_triad_stack([7, 11, 2]) == {
    "base": 7,
    "name": "major",
}, "the marks need not arrive in order"
assert name_triad_stack([0, 4, 8]) == {
    "base": 0,
    "name": "augmented",
}, "every class fits the same row so the smallest wins"
assert name_triad_stack([0, 5, 7]) == {"base": 0, "name": "quartal"}, "a quartal at zero"
assert name_triad_stack([0, 2, 7]) == {
    "base": 7,
    "name": "quartal",
}, "only one turn of this stack is in the table"
assert name_triad_stack([0, 2, 6]) == {"base": 0, "name": "narrow"}, "a narrow shape"
assert name_triad_stack([0, 3, 6]) == {"base": 0, "name": "diminished"}, "a diminished shape"
assert name_triad_stack([0, 3, 6, 9]) == {
    "base": 0,
    "name": "shrunk seventh",
}, "four classes all fitting one row"
assert name_triad_stack([0, 4, 7, 11]) == {
    "base": 0,
    "name": "major seventh",
}, "a four-class row"
assert name_triad_stack([0, 4, 7, 10]) == {
    "base": 0,
    "name": "dominant seventh",
}, "another four-class row"
assert name_triad_stack([0, 3, 7, 10]) == {
    "base": 0,
    "name": "minor seventh",
}, "a third four-class row"
assert name_triad_stack([0, 1, 2]) == {
    "base": -1,
    "name": "unknown",
}, "no turn of this stack is in the table"


def rejects(value):
    try:
        name_triad_stack(value)
    except ValueError:
        return True
    return False


assert rejects("047"), "a non-list argument is rejected"
assert rejects([]), "an empty list is rejected"
assert rejects([0, 1.5, 4]), "a fractional mark is rejected"
assert rejects([0, "4", 7]), "a non-number mark is rejected"
assert rejects([0, 12, 24]), "one class after folding is rejected"
assert rejects([0, 4]), "two classes are rejected"
print("ok")
