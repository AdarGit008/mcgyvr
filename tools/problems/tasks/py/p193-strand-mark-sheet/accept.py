from solution import strand_mark_sheet


def one(work, discard=0):
    return [{"name": "s", "share": 1000, "discard": discard, "work": work}]


def rejects(value):
    try:
        strand_mark_sheet(value)
    except ValueError:
        return True
    return False


assert strand_mark_sheet(one([[5, 5], [5, 5]])) == {
    "mark": 1000,
    "discarded": [],
}, "everything scored and nothing discarded reads 1000"

assert strand_mark_sheet(one([[8, 10], [5, 10], [9, 10]], 1)) == {
    "mark": 850,
    "discarded": ["s#1"],
}, "the weakest of three goes"

assert strand_mark_sheet(one([[1, 2], [3, 10]], 1)) == {
    "mark": 500,
    "discarded": ["s#1"],
}, "weakness is the ratio, not the raw score"

assert strand_mark_sheet(one([["absent", 10], [7, 10]])) == {
    "mark": 350,
    "discarded": [],
}, "an absent piece still occupies its availability"

assert strand_mark_sheet(one([["absent", 5], [4, 5], [3, 5]], 1)) == {
    "mark": 700,
    "discarded": ["s#0"],
}, "an absent piece is the weakest there is"

assert strand_mark_sheet(one([[1, 4], [2, 4]], 5)) == {
    "mark": 500,
    "discarded": ["s#0"],
}, "a runaway discard count still leaves the strongest piece"

assert strand_mark_sheet(one([[1, 2], [2, 4], [9, 10]], 1)) == {
    "mark": 833,
    "discarded": ["s#1"],
}, "equal ratios break toward the piece available for more"

assert strand_mark_sheet(one([[1, 2], [1, 2], [9, 10]], 1)) == {
    "mark": 833,
    "discarded": ["s#0"],
}, "identical pieces break toward the earlier position"

assert strand_mark_sheet(
    [
        {"name": "A", "share": 600, "discard": 1, "work": [[3, 5], [4, 5]]},
        {
            "name": "B",
            "share": 400,
            "discard": 2,
            "work": [[1, 3], [2, 3], ["absent", 3]],
        },
    ]
) == {"mark": 746, "discarded": ["A#0", "B#2", "B#0"]}, "strands in order"

assert rejects([]), "an empty report is rejected"
assert rejects(
    [
        {"name": "x", "share": 500, "discard": 0, "work": [[1, 1]]},
        {"name": "x", "share": 500, "discard": 0, "work": [[1, 1]]},
    ]
), "a repeated strand name is rejected"
assert rejects(
    [{"name": "x", "share": 900, "discard": 0, "work": [[1, 1]]}]
), "shares that miss 1000 are rejected"
assert rejects(one([[1, 1]], -1)), "a negative discard count is rejected"
assert rejects(one([])), "a strand with no work is rejected"
assert rejects(one([[0, 0]])), "a piece available for nothing is rejected"
assert rejects(one([[4, 3]])), "a score above its availability is rejected"
assert rejects(one([[-2, 3]])), "a negative score is rejected"
assert rejects(one([["late", 3]])), "an unknown score word is rejected"

print("ok")
