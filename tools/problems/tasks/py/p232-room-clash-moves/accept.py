from solution import plan_room_moves


def book(ident, start, end, fixed=False):
    return {"id": ident, "start": start, "end": end, "fixed": fixed}


def rejects(rows):
    try:
        plan_room_moves(rows)
    except ValueError:
        return True
    return False


assert plan_room_moves([]) == [], "an empty diary needs no moves"
assert plan_room_moves([book("a", 0, 10), book("b", 10, 20)]) == [], (
    "touching half-open spans do not clash"
)
assert plan_room_moves(
    [book("a", 0, 30), book("b", 5, 10), book("c", 12, 18)]
) == ["a"], "one long booking yields to two short ones"
assert plan_room_moves([book("b", 0, 10), book("a", 2, 10)]) == ["a"], (
    "equal ends are settled by the earlier start"
)
assert plan_room_moves(
    [
        book("p", 10, 20, True),
        book("q", 15, 25),
        book("r", 0, 5),
        book("s", 20, 30),
    ]
) == ["q"], "a movable booking overlapping a nailed one always goes"
assert plan_room_moves(
    [book("p", 0, 10, True), book("q", 20, 30, True), book("m", 5, 25)]
) == ["m"], "a booking straddling two nailed ones goes"
assert plan_room_moves(
    [
        book("w", 0, 4, True),
        book("x", 4, 12),
        book("y", 5, 8),
        book("z", 9, 11),
    ]
) == ["x"], "the gap after a nailed booking still takes the two-booking answer"
assert plan_room_moves(
    [book("g", 6, 9), book("h", 0, 7), book("i", 8, 14)]
) == ["g"], "the greedy walk keeps the pair that fits, not the first seen"
assert plan_room_moves(
    [book("p", 10, 20, True), book("q", 12, 14), book("r", 0, 30)]
) == ["r", "q"], "moved ids come back ordered by start, not by discovery"

assert rejects([book("p", 0, 10, True), book("q", 5, 15, True)]), (
    "two overlapping nailed bookings are beyond repair"
)
assert rejects([book("a", 7, 7)]), "a span of no length is rejected"
assert rejects([book("a", 0, 5), book("a", 6, 9)]), "a repeated id is rejected"
assert rejects([{"id": "a", "start": 0, "end": 5}]), (
    "a missing fixed flag is rejected"
)
assert rejects([book("", 0, 5)]), "an empty id is rejected"
print("ok")
