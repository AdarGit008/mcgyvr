from solution import match_statement_rows

book = [
    {"ref": "B1", "day": 10, "cents": 2500},
    {"ref": "B2", "day": 11, "cents": 2500},
    {"ref": "B3", "day": 20, "cents": -800},
    {"ref": "B4", "day": 30, "cents": 9999},
]
bank = [
    {"ref": "K1", "day": 12, "cents": 2500},
    {"ref": "K2", "day": 10, "cents": 2500},
    {"ref": "K3", "day": 21, "cents": -800},
    {"ref": "K4", "day": 40, "cents": 9999},
]

assert match_statement_rows(book, bank, 2) == {
    "pairs": [["B1", "K2"], ["B2", "K1"], ["B3", "K3"]],
    "bookOnly": ["B4"],
    "bankOnly": ["K4"],
}, "the closest free statement row wins, not the first listed"
assert match_statement_rows(list(reversed(book)), bank, 2) == {
    "pairs": [["B1", "K2"], ["B2", "K1"], ["B3", "K3"]],
    "bookOnly": ["B4"],
    "bankOnly": ["K4"],
}, "the walk order comes from the days, not the list order"
assert match_statement_rows(book, bank, 0) == {
    "pairs": [["B1", "K2"]],
    "bookOnly": ["B2", "B3", "B4"],
    "bankOnly": ["K1", "K3", "K4"],
}, "a zero tolerance keeps only the same-day pair"
assert match_statement_rows([], [], 3) == {
    "pairs": [],
    "bookOnly": [],
    "bankOnly": [],
}, "two empty statements reconcile to nothing"
assert match_statement_rows(
    [{"ref": "A", "day": 10, "cents": 100}],
    [{"ref": "Z", "day": 8, "cents": 100}, {"ref": "Y", "day": 12, "cents": 100}],
    2,
) == {
    "pairs": [["A", "Z"]],
    "bookOnly": [],
    "bankOnly": ["Y"],
}, "an equal distance goes to the earlier day"
assert match_statement_rows(
    [{"ref": "A", "day": 10, "cents": 100}],
    [{"ref": "Y", "day": 12, "cents": 100}, {"ref": "X", "day": 12, "cents": 100}],
    2,
) == {
    "pairs": [["A", "X"]],
    "bookOnly": [],
    "bankOnly": ["Y"],
}, "an equal distance on an equal day goes to the smaller ref"
assert match_statement_rows(
    [{"ref": "B9", "day": 5, "cents": 700}, {"ref": "B1", "day": 5, "cents": 700}],
    [{"ref": "K9", "day": 4, "cents": 700}],
    1,
) == {
    "pairs": [["B1", "K9"]],
    "bookOnly": ["B9"],
    "bankOnly": [],
}, "a shared day is walked by ascending ref"
assert match_statement_rows(
    [{"ref": "A", "day": 3, "cents": 100}],
    [{"ref": "Z", "day": 3, "cents": -100}],
    5,
) == {
    "pairs": [],
    "bookOnly": ["A"],
    "bankOnly": ["Z"],
}, "a sign difference is not the same amount"
assert match_statement_rows(
    [{"ref": "A", "day": 3, "cents": 100, "note": "kept"}],
    [{"ref": "Z", "day": 3, "cents": 100, "note": "kept"}],
    0,
) == {
    "pairs": [["A", "Z"]],
    "bookOnly": [],
    "bankOnly": [],
}, "spare fields do not disturb a pairing"


def rejects(a, b, tolerance):
    try:
        match_statement_rows(a, b, tolerance)
    except ValueError:
        return True
    return False


assert rejects(
    [{"ref": "A", "day": 1, "cents": 5}, {"ref": "A", "day": 2, "cents": 5}], [], 1
), "a repeated ref is rejected"
assert rejects([{"ref": "", "day": 1, "cents": 5}], [], 1), "an empty ref is rejected"
assert rejects([{"ref": "A", "day": 1}], [], 1), "a missing field is rejected"
assert rejects([{"ref": "A", "day": 1.5, "cents": 5}], [], 1), "a fractional day is rejected"
assert rejects([{"ref": "A", "day": 1, "cents": 5.5}], [], 1), "fractional cents are rejected"
assert rejects([{"ref": "A", "day": 1, "cents": 0}], [], 1), "a zero amount is rejected"
assert rejects([], [{"ref": "K", "day": 1, "cents": 5}], -1), "a negative tolerance is rejected"
assert rejects([], [], 1.5), "a fractional tolerance is rejected"
assert rejects("rows", [], 1), "a string cash book is rejected"
print("ok")
