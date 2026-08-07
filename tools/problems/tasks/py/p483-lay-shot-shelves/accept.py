from solution import lay_shot_shelves

STRIP = {"per_row": 3, "cell": 60, "lead": 4}
SHOTS = [
    {"name": "s1", "across": 60, "down": 40},
    {"name": "s2", "across": 30, "down": 40},
    {"name": "s3", "across": 45, "down": 30},
    {"name": "s4", "across": 7, "down": 3},
    {"name": "s5", "across": 8, "down": 8},
]

assert lay_shot_shelves(SHOTS, STRIP) == {
    "rows": [
        {"names": ["s1", "s2", "s3"], "deep": 80},
        {"names": ["s4", "s5"], "deep": 60},
    ],
    "deep": 144,
}, "a row runs as deep as its deepest frame and one lead joins the two rows"

assert lay_shot_shelves(
    [{"name": "only", "across": 7, "down": 3}],
    {"per_row": 3, "cell": 60, "lead": 9},
) == {
    "rows": [{"names": ["only"], "deep": 26}],
    "deep": 26,
}, "a remainder pushes the depth up and a single row carries no lead"

assert lay_shot_shelves(
    [{"name": "even", "across": 20, "down": 10}],
    {"per_row": 4, "cell": 100, "lead": 3},
) == {
    "rows": [{"names": ["even"], "deep": 50}],
    "deep": 50,
}, "an exact division is not pushed up"

assert lay_shot_shelves(SHOTS[:3], {"per_row": 1, "cell": 60, "lead": 5}) == {
    "rows": [
        {"names": ["s1"], "deep": 40},
        {"names": ["s2"], "deep": 80},
        {"names": ["s3"], "deep": 40},
    ],
    "deep": 170,
}, "three rows carry two leads"

assert (
    lay_shot_shelves(SHOTS, {"per_row": 3, "cell": 60, "lead": 0})["deep"] == 140
), "a lead of nought adds nothing"
assert [
    len(row["names"])
    for row in lay_shot_shelves(SHOTS, {"per_row": 5, "cell": 60, "lead": 7})["rows"]
] == [5], "one row holds every frame when per_row allows it"


def rejects(shots, strip):
    try:
        lay_shot_shelves(shots, strip)
    except ValueError:
        return True
    return False


assert rejects("nope", STRIP), "shots must be a list"
assert rejects([], STRIP), "an empty list is rejected"
assert rejects(["s1"], STRIP), "a shot must be a record"
assert rejects([{"name": "", "across": 4, "down": 4}], STRIP), "an empty name is rejected"
assert rejects(
    [{"name": "twin", "across": 4, "down": 4}, {"name": "twin", "across": 5, "down": 5}],
    STRIP,
), "a repeated name is rejected"
assert rejects([{"name": "z", "across": 0, "down": 4}], STRIP), "a side of nought is rejected"
assert rejects(
    [{"name": "z", "across": 4, "down": 1.5}], STRIP
), "a fractional side is rejected"
assert rejects([{"name": "z", "across": 4, "down": 4}], "strip"), "strip must be a record"
assert rejects(
    [{"name": "z", "across": 4, "down": 4}], {"per_row": 0, "cell": 60, "lead": 4}
), "a per_row of nought is rejected"
assert rejects(
    [{"name": "z", "across": 4, "down": 4}], {"per_row": 3, "cell": 60, "lead": -2}
), "a negative lead is rejected"
print("ok")
