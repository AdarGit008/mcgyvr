from solution import meeting_points

assert meeting_points(0, 4, 0, 6, 3) == [
    0,
    12,
    24,
], "two ladders from the same start meet on their least common multiple"
assert meeting_points(1, 4, 3, 6, 3) == [
    9,
    21,
    33,
], "offset starts with strides sharing a factor"
assert meeting_points(10, 3, 4, 5, 2) == [
    19,
    34,
], "the earliest landing sits at or beyond both starts"
assert meeting_points(5, 1, 0, 1, 3) == [
    5,
    6,
    7,
], "strides of one meet everywhere at or beyond the later start"
assert meeting_points(7, 7, 7, 7, 4) == [
    7,
    14,
    21,
    28,
], "two identical ladders meet at every rung"
assert meeting_points(0, 2, 1, 4, 5) == [
], "an even ladder and an odd one never land together"
assert meeting_points(0, 4, 0, 6, 0) == [
], "a count of nothing asks for no landings at all"
assert meeting_points(1, 4, 3, 6, 1) == [
    9
], "a count of one hands back just the earliest landing"
assert meeting_points(0, 100000, 0, 99999, 2) == [
    0,
    9999900000,
], "strides at the ceiling still land exactly"


def rejects(*args):
    try:
        meeting_points(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 0, 0, 4, 2), "a stride of nothing is rejected"
assert rejects(0, 4, 0, -6, 2), "a negative stride is rejected"
assert rejects(0, 100001, 0, 4, 2), "a stride past the ceiling is rejected"
assert rejects(-1, 4, 0, 6, 2), "a negative start is rejected"
assert rejects(1000001, 4, 0, 6, 2), "a start past the ceiling is rejected"
assert rejects(0, 4, 0, 6, 21), "a count past twenty is rejected"
assert rejects(0, 4, 0, 6, -1), "a negative count is rejected"
assert rejects(0.5, 4, 0, 6, 2), "a fractional start is rejected"
assert rejects("0", 4, 0, 6, 2), "a non-numeric start is rejected"
print("ok")
