from solution import recorder_snapshot

assert recorder_snapshot(3, [10, 11, 12, 13]) == {
    "order": [11, 12, 13],
    "head": 1,
    "overwritten": 1,
    "starved": 0,
}, "one write past the end drops the oldest frame and moves the marker"
assert recorder_snapshot(3, [10, 11, -1, 12, 13, 14]) == {
    "order": [12, 13, 14],
    "head": 2,
    "overwritten": 1,
    "starved": 0,
}, "an eject partway through shifts where later writes land"
assert recorder_snapshot(2, [-1, -1, 5]) == {
    "order": [5],
    "head": 0,
    "overwritten": 0,
    "starved": 2,
}, "ejects against an empty recorder are tallied, not applied"
assert recorder_snapshot(1, [7, 8, 9]) == {
    "order": [9],
    "head": 0,
    "overwritten": 2,
    "starved": 0,
}, "a single slot keeps only the newest frame"
assert recorder_snapshot(4, []) == {
    "order": [],
    "head": 0,
    "overwritten": 0,
    "starved": 0,
}, "an empty script leaves the recorder untouched"
assert recorder_snapshot(3, [1, 2, 3, 4, 5, -1, -1]) == {
    "order": [5],
    "head": 1,
    "overwritten": 2,
    "starved": 0,
}, "ejects after a wrap leave the marker mid-cycle"
assert recorder_snapshot(2, [4, 5, -1, -1, -1, 6]) == {
    "order": [6],
    "head": 0,
    "overwritten": 0,
    "starved": 1,
}, "a drained recorder writes to the slot the marker already points at"
assert recorder_snapshot(4, [1, 2, 3, 4, 5, 6]) == {
    "order": [3, 4, 5, 6],
    "head": 2,
    "overwritten": 2,
    "starved": 0,
}, "the surviving frames read oldest first even when the cycle has turned"
assert recorder_snapshot(3, [0, 0, 0, 0]) == {
    "order": [0, 0, 0],
    "head": 1,
    "overwritten": 1,
    "starved": 0,
}, "frame zero is an ordinary frame number"


def rejects(slots, script):
    try:
        recorder_snapshot(slots, script)
    except ValueError:
        return True
    return False


assert rejects(0, [1]), "a zero slot count is rejected"
assert rejects(2.5, [1]), "a fractional slot count is rejected"
assert rejects(2, "12"), "a non-list script is rejected"
assert rejects(2, [-2]), "an entry below -1 is rejected"
assert rejects(2, [1.5]), "a fractional frame is rejected"
assert rejects(2, ["3"]), "a frame given as text is rejected"
print("ok")
