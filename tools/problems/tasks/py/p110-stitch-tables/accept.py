import copy

from solution import stitch_tables

crew = [
    {"badge": "b1", "post": "deck"},
    {"badge": "b2", "post": "helm"},
    {"badge": "b3", "post": "galley"},
]
shifts = [
    {"badge": "b2", "watch": 4},
    {"badge": "b1", "watch": 2},
]

assert stitch_tables(crew, shifts, "badge", "inner") == [
    {"badge": "b1", "post": "deck", "watch": 2},
    {"badge": "b2", "post": "helm", "watch": 4},
], "inner keeps matched records in left order"
assert stitch_tables(crew, shifts, "badge", "left") == [
    {"badge": "b1", "post": "deck", "watch": 2},
    {"badge": "b2", "post": "helm", "watch": 4},
    {"badge": "b3", "post": "galley", "watch": None},
], "left mode keeps the unmatched record with a null column"
assert stitch_tables(
    [{"badge": "b1"}, {"badge": "b1", "post": "bow"}],
    [{"badge": "b1", "watch": 7, "berth": "aft"}],
    "badge",
    "inner",
) == [
    {"badge": "b1", "watch": 7, "berth": "aft"},
    {"badge": "b1", "post": "bow", "watch": 7, "berth": "aft"},
], "repeated left keys each join, ragged records keep their own columns"
assert stitch_tables(
    [{"badge": "b9", "post": "deck"}],
    [{"badge": "b1", "watch": 1}, {"badge": "b2"}],
    "badge",
    "left",
) == [
    {"badge": "b9", "post": "deck", "watch": None}
], "null filling covers every right column seen anywhere"
assert (
    stitch_tables([{"badge": "b9"}], shifts, "badge", "inner") == []
), "inner with no matches is empty"
assert stitch_tables([], shifts, "badge", "left") == [], "an empty left table"
before = copy.deepcopy(crew)
stitch_tables(crew, shifts, "badge", "left")
assert crew == before, "the left table is not modified"


def rejects(left, right, key, mode):
    try:
        stitch_tables(left, right, key, mode)
    except ValueError:
        return True
    return False


assert rejects(
    crew, [{"badge": "b1"}, {"badge": "b1"}], "badge", "inner"
), "a repeated right key is rejected"
assert rejects(
    crew, [{"badge": "b1", "post": "aft"}], "badge", "inner"
), "a shared non-key column is rejected"
assert rejects(
    [{"badge": "b8", "post": "x"}], [{"badge": "b1", "post": "aft"}], "badge", "inner"
), "the column clash is detected even with no matching keys"
assert rejects(
    [{"post": "deck"}], shifts, "badge", "inner"
), "a record missing the key column is rejected"
assert rejects(
    [{"badge": 7}], shifts, "badge", "inner"
), "a non-string key value is rejected"
assert rejects(crew, shifts, "badge", "outer"), "an unknown mode is rejected"
print("ok")
