from solution import trace_arrears_steps

assert trace_arrears_steps(
    1000,
    20,
    [
        {"kind": "check", "day": 20},
        {"kind": "check", "day": 21},
        {"kind": "check", "day": 29},
        {"kind": "check", "day": 30},
        {"kind": "pay", "day": 31, "cents": 400},
        {"kind": "check", "day": 40},
        {"kind": "check", "day": 56},
        {"kind": "check", "day": 75},
        {"kind": "check", "day": 76},
        {"kind": "pay", "day": 80, "cents": 600},
        {"kind": "check", "day": 200},
    ],
) == [
    "current",
    "reminder",
    "reminder",
    "warning",
    "reminder",
    "demand",
    "demand",
    "referred",
    "settled",
], "every band edge, a re-anchoring payment and the closing one"

assert trace_arrears_steps(100, 50, [{"kind": "check", "day": 10}]) == [
    "current"
], "a check before the due day reads current"

assert trace_arrears_steps(
    500, 0, [{"kind": "pay", "day": 1, "cents": 900}, {"kind": "check", "day": 2}]
) == ["settled"], "paying more than is owed closes the matter"

assert trace_arrears_steps(
    500,
    0,
    [
        {"kind": "pay", "day": 3, "cents": 499},
        {"kind": "check", "day": 12},
        {"kind": "check", "day": 13},
    ],
) == [
    "reminder",
    "warning",
], "one cent left over keeps the account open and re-anchored"

assert trace_arrears_steps(90, 4, []) == [], "no checks put out no labels"

assert trace_arrears_steps(
    90,
    4,
    [
        {"kind": "pay", "day": 4, "cents": 90},
        {"kind": "pay", "day": 9, "cents": 90},
        {"kind": "check", "day": 400},
    ],
) == ["settled"], "a payment against a closed account leaves it closed"


def rejects(opening, due_day, events):
    try:
        trace_arrears_steps(opening, due_day, events)
    except ValueError:
        return True
    return False


assert rejects(0, 4, []), "an opening sum below one is rejected"
assert rejects(90, -4, []), "a due day below nought is rejected"
assert rejects(90, 4, "nope"), "a non-list of events is rejected"
assert rejects(90, 4, [{"kind": "nudge", "day": 5}]), "an unknown kind is rejected"
assert rejects(
    90, 4, [{"kind": "check", "day": 5, "cents": 1}]
), "a check carrying cents is rejected"
assert rejects(90, 4, [{"kind": "pay", "day": 5}]), "a payment without cents is rejected"
assert rejects(
    90, 4, [{"kind": "pay", "day": 5, "cents": 0}]
), "a payment of nothing is rejected"
assert rejects(
    90, 4, [{"kind": "check", "day": 8}, {"kind": "check", "day": 7}]
), "a day stepping backwards is rejected"
assert rejects(
    90, 4, [{"kind": "check", "day": 2.5}]
), "a day that is not whole is rejected"
print("ok")
