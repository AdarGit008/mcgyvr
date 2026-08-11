from solution import reserve_court

assert reserve_court([], [60, 120], [0, 600]) == [[60, 120]], "empty sheet"
assert reserve_court([[0, 60], [180, 240]], [90, 150], [0, 600]) == [
    [0, 60],
    [90, 150],
    [180, 240],
], "slot lands between bookings"
assert reserve_court([[0, 60]], [60, 90], [0, 600]) == [
    [0, 60],
    [60, 90],
], "touching a booking's end is allowed"
assert reserve_court([[120, 180]], [60, 120], [0, 600]) == [
    [60, 120],
    [120, 180],
], "touching a booking's start is allowed"
assert reserve_court([[0, 60], [90, 120]], [60, 90], [0, 600]) == [
    [0, 60],
    [60, 90],
    [90, 120],
], "a slot may touch on both sides"
assert reserve_court([], [0, 600], [0, 600]) == [[0, 600]], "whole day fits"
assert reserve_court([[300, 360], [0, 60]], [120, 180], [0, 600]) == [
    [0, 60],
    [120, 180],
    [300, 360],
], "bookings arrive unsorted"
sheet = [[300, 360], [0, 60]]
reserve_court(sheet, [120, 180], [0, 600])
assert sheet == [[300, 360], [0, 60]], "the given sheet is untouched"


def rejects(*args):
    try:
        reserve_court(*args)
    except Exception:
        return True
    return False


assert rejects([[50, 100]], [90, 150], [0, 600]), "overlap rejected"
assert rejects([[0, 200]], [50, 100], [0, 600]), "contained slot rejected"
assert rejects([], [30, 90], [60, 600]), "slot before opening rejected"
assert rejects([], [540, 660], [0, 600]), "slot past closing rejected"
assert rejects([], [10.5, 60], [0, 600]), "fractional bound rejected"
assert rejects([], [120, 60], [0, 600]), "reversed slot rejected"
assert rejects([], [60, 120], [600, 0]), "reversed hours rejected"
assert rejects([[0, 100], [50, 150]], [200, 260], [0, 600]), "overlapping sheet rejected"
assert rejects([[0]], [200, 260], [0, 600]), "one-item booking rejected"
assert rejects([[60, 0]], [200, 260], [0, 600]), "reversed booking rejected"
print("ok")
