from solution import assign_track_columns


def of(rows):
    return [{"label": label, "first": first, "last": last} for label, first, last in rows]


def rejects(spans):
    try:
        assign_track_columns(spans)
    except ValueError:
        return True
    return False


assert assign_track_columns([]) == [], "nothing to lay out"
assert assign_track_columns(of([("a", 0, 0)])) == [0], "one span on the first track"
assert assign_track_columns(of([("a", 0, 2), ("b", 3, 4)])) == [
    0,
    0,
], "spans that never share a row reuse the track"
assert assign_track_columns(of([("a", 0, 2), ("b", 2, 4)])) == [
    0,
    1,
], "one shared row is enough to force a second track"
assert assign_track_columns(of([("a", 0, 1), ("b", 1, 2), ("c", 2, 3)])) == [
    0,
    1,
    0,
], "a chain of spans overlapping only at their edges"
assert assign_track_columns(of([("a", 0, 4), ("b", 1, 2), ("c", 3, 4)])) == [
    0,
    1,
    1,
], "the second track is free again below the span that held it"
assert assign_track_columns(of([("a", 0, 5), ("b", 0, 5), ("c", 0, 5)])) == [
    0,
    1,
    2,
], "three spans covering the same rows need three tracks"
assert assign_track_columns(
    of([("a", 0, 3), ("b", 1, 4), ("c", 2, 5), ("d", 6, 7)])
) == [0, 1, 2, 0], "a staircase of overlaps and then a clear span"
assert assign_track_columns(of([("a", 4, 5), ("b", 0, 1), ("c", 2, 3)])) == [
    0,
    0,
    0,
], "spans arriving out of order still stack on one track"
assert rejects("nope"), "a bare string is rejected"
assert rejects([7]), "a span that is not a mapping"
assert rejects([{"first": 0, "last": 1}]), "a span with no label is rejected"
assert rejects([{"label": "a", "first": 0.5, "last": 1}]), "a fractional row is rejected"
assert rejects(of([("a", -1, 1)])), "a row below zero is rejected"
assert rejects(of([("a", 3, 1)])), "a span ending before it starts is rejected"
assert rejects(of([("a", 0, 1), ("a", 2, 3)])), "a repeated label is rejected"
print("ok")
