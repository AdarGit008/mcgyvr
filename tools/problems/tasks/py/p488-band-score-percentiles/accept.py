from solution import band_score_percentiles

SITTERS = [
    {"tag": "t1", "score": 10},
    {"tag": "t2", "score": 40},
    {"tag": "t3", "score": 40},
    {"tag": "t4", "score": 55},
    {"tag": "t5", "score": 70},
    {"tag": "t6", "score": 70},
    {"tag": "t7", "score": 70},
    {"tag": "t8", "score": 95},
]
CUTS = [25, 50, 75]
NAMES = ["low", "mid", "high", "top"]

OUT = band_score_percentiles(SITTERS, CUTS, NAMES)
assert OUT["rows"] == [
    {"tag": "t1", "stand": 0, "band": "low"},
    {"tag": "t2", "stand": 12, "band": "low"},
    {"tag": "t3", "stand": 12, "band": "low"},
    {"tag": "t4", "stand": 37, "band": "mid"},
    {"tag": "t5", "stand": 50, "band": "high"},
    {"tag": "t6", "stand": 50, "band": "high"},
    {"tag": "t7", "stand": 50, "band": "high"},
    {"tag": "t8", "stand": 87, "band": "top"},
], "equal scores share a standing and a standing on a cut takes the band above"
assert OUT["tally"] == [
    {"band": "low", "count": 3},
    {"band": "mid", "count": 1},
    {"band": "high", "count": 3},
    {"band": "top", "count": 1},
], "the tally follows the order the names were listed"

assert band_score_percentiles(
    [
        {"tag": "a", "score": 1},
        {"tag": "b", "score": 2},
        {"tag": "c", "score": 3},
        {"tag": "d", "score": 4},
    ],
    [50],
    ["under", "over"],
) == {
    "rows": [
        {"tag": "a", "stand": 0, "band": "under"},
        {"tag": "b", "stand": 25, "band": "under"},
        {"tag": "c", "stand": 50, "band": "over"},
        {"tag": "d", "stand": 75, "band": "over"},
    ],
    "tally": [{"band": "under", "count": 2}, {"band": "over", "count": 2}],
}, "a single cut splits four sitters in half"

assert band_score_percentiles(
    [{"tag": "x", "score": 8}, {"tag": "y", "score": 8}, {"tag": "z", "score": 8}],
    [10, 90],
    ["a", "b", "c"],
) == {
    "rows": [
        {"tag": "x", "stand": 0, "band": "a"},
        {"tag": "y", "stand": 0, "band": "a"},
        {"tag": "z", "stand": 0, "band": "a"},
    ],
    "tally": [
        {"band": "a", "count": 3},
        {"band": "b", "count": 0},
        {"band": "c", "count": 0},
    ],
}, "one score for everybody puts everybody in the first band"

assert band_score_percentiles([{"tag": "solo", "score": 0}], [1], ["first", "second"]) == {
    "rows": [{"tag": "solo", "stand": 0, "band": "first"}],
    "tally": [{"band": "first", "count": 1}, {"band": "second", "count": 0}],
}, "one sitter stands at nought"

assert band_score_percentiles(SITTERS, [1, 99], ["bottom", "middle", "ceiling"])[
    "tally"
] == [
    {"band": "bottom", "count": 1},
    {"band": "middle", "count": 7},
    {"band": "ceiling", "count": 0},
], "wide cuts leave the top band empty"


def rejects(sitters, cuts, names):
    try:
        band_score_percentiles(sitters, cuts, names)
    except ValueError:
        return True
    return False


assert rejects("no", CUTS, NAMES), "sitters must be a list"
assert rejects([], CUTS, NAMES), "an empty roll is rejected"
assert rejects([5], CUTS, NAMES), "a sitter must be a record"
assert rejects([{"tag": "", "score": 4}], CUTS, NAMES), "an empty tag is rejected"
assert rejects(
    [{"tag": "same", "score": 4}, {"tag": "same", "score": 5}], CUTS, NAMES
), "a repeated tag is rejected"
assert rejects([{"tag": "a", "score": -1}], CUTS, NAMES), "a negative score is rejected"
assert rejects([{"tag": "a", "score": 4.5}], CUTS, NAMES), "a fractional score is rejected"
assert rejects(SITTERS, [], []), "an empty cut list is rejected"
assert rejects(SITTERS, [0, 50], ["a", "b", "c"]), "a cut of nought is rejected"
assert rejects(SITTERS, [50, 100], ["a", "b", "c"]), "a cut of a hundred is rejected"
assert rejects(SITTERS, [50, 50], ["a", "b", "c"]), "cuts that do not rise are rejected"
assert rejects(SITTERS, [25, 50], ["a", "b"]), "too few names are rejected"
assert rejects(SITTERS, [25, 50], ["a", "", "c"]), "an empty name is rejected"
assert rejects(SITTERS, [25, 50], ["a", "a", "c"]), "a repeated name is rejected"
print("ok")
