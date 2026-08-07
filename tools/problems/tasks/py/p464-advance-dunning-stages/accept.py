from solution import advance_dunning_stages

BOOK = [
    {"id": "F", "due": 159, "cents": 90},
    {"id": "A", "due": 100, "cents": 5000},
    {"id": "C", "due": 50, "cents": 1000},
    {"id": "H", "due": 145, "cents": 90},
    {"id": "B", "due": 130, "cents": 3000},
    {"id": "G", "due": 160, "cents": 90},
    {"id": "D", "due": 200, "cents": 800},
    {"id": "E", "due": 60, "cents": 250},
]
TRAIL = [
    {"kind": "payment", "day": 120, "invoice": "A", "cents": 1000},
    {"kind": "dispute", "day": 130, "invoice": "B"},
    {"kind": "payment", "day": 140, "invoice": "C", "cents": 1000},
    {"kind": "release", "day": 150, "invoice": "B"},
    {"kind": "dispute", "day": 155, "invoice": "A"},
]

assert advance_dunning_stages(BOOK, TRAIL, 160) == [
    {"id": "A", "stage": "final", "owed": 4000},
    {"id": "B", "stage": "reminder", "owed": 3000},
    {"id": "C", "stage": "settled", "owed": 0},
    {"id": "D", "stage": "current", "owed": 800},
    {"id": "E", "stage": "collections", "owed": 250},
    {"id": "F", "stage": "reminder", "owed": 90},
    {"id": "G", "stage": "current", "owed": 90},
    {"id": "H", "stage": "notice", "owed": 90},
], "every band, the settled case and ascending id order together"

assert advance_dunning_stages([{"id": "z", "due": 10, "cents": 500}], [], 39) == [
    {"id": "z", "stage": "notice", "owed": 500}
], "an untouched invoice ages from its due day"

assert advance_dunning_stages(
    [{"id": "z", "due": 10, "cents": 500}],
    [
        {"kind": "payment", "day": 20, "invoice": "z", "cents": 100},
        {"kind": "payment", "day": 35, "invoice": "z", "cents": 100},
    ],
    39,
) == [
    {"id": "z", "stage": "reminder", "owed": 300}
], "the most recent payment carries the anchor forward"

assert advance_dunning_stages(
    [{"id": "z", "due": 100, "cents": 500}],
    [
        {"kind": "dispute", "day": 50, "invoice": "z"},
        {"kind": "release", "day": 70, "invoice": "z"},
    ],
    120,
) == [
    {"id": "z", "stage": "notice", "owed": 500}
], "a freeze wholly before the anchor holds nothing back"

assert advance_dunning_stages(
    [{"id": "z", "due": 100, "cents": 500}],
    [
        {"kind": "dispute", "day": 90, "invoice": "z"},
        {"kind": "release", "day": 110, "invoice": "z"},
    ],
    130,
) == [
    {"id": "z", "stage": "notice", "owed": 500}
], "only the part of a freeze after the anchor is held back"

assert advance_dunning_stages(
    [{"id": "z", "due": 0, "cents": 400}],
    [{"kind": "payment", "day": 5, "invoice": "z", "cents": 900}],
    500,
) == [
    {"id": "z", "stage": "settled", "owed": 0}
], "an overpayment settles and never owes below nought"

assert advance_dunning_stages([], [], 7) == [], "an empty book reports nothing"


def rejects(invoices, events, report_day):
    try:
        advance_dunning_stages(invoices, events, report_day)
    except ValueError:
        return True
    return False


assert rejects(
    [{"id": "z", "due": 1, "cents": 2, "note": "x"}], [], 5
), "an invoice with a spare key is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}, {"id": "z", "due": 3, "cents": 4}], [], 5
), "two invoices sharing an id are rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}],
    [{"kind": "payment", "day": 2, "invoice": "q", "cents": 1}],
    5,
), "an event naming an unheld invoice is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}],
    [{"kind": "release", "day": 2, "invoice": "z"}],
    5,
), "releasing an unfrozen invoice is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}],
    [
        {"kind": "dispute", "day": 2, "invoice": "z"},
        {"kind": "dispute", "day": 3, "invoice": "z"},
    ],
    5,
), "disputing a frozen invoice again is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}],
    [{"kind": "payment", "day": 9, "invoice": "z", "cents": 1}],
    5,
), "an event past the reporting day is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}],
    [
        {"kind": "dispute", "day": 4, "invoice": "z"},
        {"kind": "release", "day": 3, "invoice": "z"},
    ],
    5,
), "an event day stepping backwards is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 0}], [], 5
), "an invoice for nothing is rejected"
assert rejects(
    [{"id": "z", "due": 1, "cents": 2}], [], -1
), "a reporting day below nought is rejected"
print("ok")
