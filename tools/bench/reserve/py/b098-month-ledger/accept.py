from solution import month_ledger

assert month_ledger([["2026-03-04", 90]]) == [
    ["2026-03", 90, 1]
], "a single entry makes one row"
assert month_ledger([["2026-03-04", 90], ["2026-03-11", 30]]) == [
    ["2026-03", 120, 2]
], "entries of one month sum"
assert month_ledger([["2026-01-05", 10], ["2026-02-06", 20]]) == [
    ["2026-01", 10, 1],
    ["2026-02", 20, 1],
], "neighbouring months stay apart"
assert month_ledger([["2026-10-01", 5], ["2026-01-02", 7]]) == [
    ["2026-01", 7, 1],
    ["2026-10", 5, 1],
], "January and October stay apart and sort"
assert month_ledger([["2025-12-31", 15], ["2026-01-01", 15]]) == [
    ["2025-12", 15, 1],
    ["2026-01", 15, 1],
], "a year boundary splits rows"
assert month_ledger([["2026-06-01", 1], ["2026-04-01", 2], ["2026-06-02", 3]]) == [
    ["2026-04", 2, 1],
    ["2026-06", 4, 2],
], "unordered entries come back sorted"
assert month_ledger([]) == [], "no entries means no rows"


def rejects(entries):
    try:
        month_ledger(entries)
    except ValueError:
        return True
    return False


assert rejects([["2026-3-4", 5]]), "a malformed stamp is rejected"
assert rejects([["2026-13-01", 5]]), "month 13 is rejected"
assert rejects([["2026-02-00", 5]]), "day zero is rejected"
assert rejects([["2026-02-02", 0]]), "zero minutes are rejected"
assert rejects([["2026-02-02", 90.5]]), "fractional minutes are rejected"
print("ok")
