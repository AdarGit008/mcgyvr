from solution import settle_plan_timeline

assert settle_plan_timeline(7, 100, []) == {
    "legs": [{"from": 1, "to": 7, "days": 7, "cents": 100}],
    "total": 100,
}, "no change at all leaves one leg at the whole price"

assert settle_plan_timeline(1, 500, []) == {
    "legs": [{"from": 1, "to": 1, "days": 1, "cents": 500}],
    "total": 500,
}, "a one-day period"

assert settle_plan_timeline(30, 1000, [{"day": 11, "cents": 2500}, {"day": 21, "cents": 400}]) == {
    "legs": [
        {"from": 1, "to": 10, "days": 10, "cents": 333},
        {"from": 11, "to": 20, "days": 10, "cents": 833},
        {"from": 21, "to": 30, "days": 10, "cents": 134},
    ],
    "total": 1300,
}, "the pot pays out on the last leg"

assert settle_plan_timeline(10, 333, [{"day": 6, "cents": 333}]) == {
    "legs": [
        {"from": 1, "to": 5, "days": 5, "cents": 166},
        {"from": 6, "to": 10, "days": 5, "cents": 167},
    ],
    "total": 333,
}, "an unchanged price still adds back to the whole period"

assert settle_plan_timeline(
    4, 10, [{"day": 2, "cents": 10}, {"day": 3, "cents": 10}, {"day": 4, "cents": 10}]
) == {
    "legs": [
        {"from": 1, "to": 1, "days": 1, "cents": 2},
        {"from": 2, "to": 2, "days": 1, "cents": 3},
        {"from": 3, "to": 3, "days": 1, "cents": 2},
        {"from": 4, "to": 4, "days": 1, "cents": 3},
    ],
    "total": 10,
}, "a change every day, the pot firing on alternate legs"

assert settle_plan_timeline(5, 0, [{"day": 3, "cents": 1000}]) == {
    "legs": [
        {"from": 1, "to": 2, "days": 2, "cents": 0},
        {"from": 3, "to": 5, "days": 3, "cents": 600},
    ],
    "total": 600,
}, "a free opening leg costs nothing"

assert settle_plan_timeline(30, 999, [{"day": 30, "cents": 100}]) == {
    "legs": [
        {"from": 1, "to": 29, "days": 29, "cents": 965},
        {"from": 30, "to": 30, "days": 1, "cents": 4},
    ],
    "total": 969,
}, "a change on the very last day"


def rejects(period_days, opening_cents, changes):
    try:
        settle_plan_timeline(period_days, opening_cents, changes)
    except ValueError:
        return True
    return False


assert rejects(0, 100, []), "a period of no days"
assert rejects(2.5, 100, []), "a fractional period"
assert rejects(30, -1, []), "a negative opening price"
assert rejects(30, 100, 4), "changes that are not a list"
assert rejects(30, 100, [5]), "a change that is not a record"
assert rejects(30, 100, [{"day": 1, "cents": 50}]), "a change on the period's first day"
assert rejects(30, 100, [{"day": 31, "cents": 50}]), "a change past the period"
assert rejects(30, 100, [{"day": 2.5, "cents": 50}]), "a fractional change day"
assert rejects(30, 100, [{"day": 5, "cents": -1}]), "a negative change price"
assert rejects(30, 100, [{"day": 5, "cents": 10}, {"day": 5, "cents": 20}]), "two on one day"
assert rejects(30, 100, [{"day": 9, "cents": 10}, {"day": 3, "cents": 20}]), "days out of order"
print("ok")
