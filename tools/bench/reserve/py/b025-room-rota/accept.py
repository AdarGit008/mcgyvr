from solution import assign_rooms, peak_rooms, spans_overlap

assert assign_rooms([]) == [], "no meetings, no rooms"
assert assign_rooms([[3, 6]]) == [0], "one meeting takes room zero"
assert assign_rooms([[0, 10], [10, 20]]) == [0, 0], "touching reuses"
assert assign_rooms([[0, 10], [5, 15]]) == [0, 1], "overlap opens a room"
assert assign_rooms([[0, 10], [5, 15], [12, 20]]) == [
    0,
    1,
    0,
], "a freed room is reused first"
assert assign_rooms([[10, 20], [0, 15]]) == [1, 0], "result aligns with input"
assert assign_rooms([[5, 30], [5, 10]]) == [1, 0], "start tie seated by end"
assert assign_rooms([[3, 6], [3, 6]]) == [0, 1], "identical meetings by position"
assert assign_rooms([[0, 10], [2, 12], [4, 14]]) == [
    0,
    1,
    2,
], "three concurrent meetings"
assert assign_rooms([[0, 30], [5, 10], [10, 15], [35, 40]]) == [
    0,
    1,
    1,
    0,
], "a longer day settles into two rooms"
assert peak_rooms([]) == 0, "no meetings need no rooms"
assert peak_rooms([[0, 10], [2, 12], [4, 14]]) == 3, "peak of three"
assert peak_rooms([[0, 30], [5, 10], [10, 15], [35, 40]]) == 2, "peak of two"
assert spans_overlap([0, 10], [5, 15]) is True, "overlapping spans"
assert spans_overlap([0, 10], [10, 20]) is False, "touching spans do not"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(assign_rooms, [[5, 2]]), "reversed meeting rejected"
assert rejects(assign_rooms, [[1, 2.5]]), "fractional endpoint"
assert rejects(spans_overlap, [4, 2], [0, 10]), "reversed span"
print("ok")
