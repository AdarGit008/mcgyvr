from solution import audit_ringing_line

assert audit_ringing_line(
    [
        [1, 2, 3, 4],
        [2, 1, 4, 3],
        [2, 4, 1, 3],
        [4, 2, 3, 1],
        [4, 3, 2, 1],
        [3, 4, 1, 2],
        [3, 1, 4, 2],
        [1, 3, 2, 4],
        [1, 2, 3, 4],
    ]
) == {"ok": True, "fault": "", "row": 0}, "a line that comes round cleanly is clean"

assert audit_ringing_line([[1, 2, 3, 4], [3, 1, 2, 4]]) == {
    "ok": False,
    "fault": "jump",
    "row": 2,
}, "a bell shifting two places is a jump even though the bells are all there"

assert audit_ringing_line([[1, 2, 3, 4], [1, 2, 3, 3]]) == {
    "ok": False,
    "fault": "shape",
    "row": 2,
}, "a row holding a bell twice is faulted on shape"

assert audit_ringing_line(
    [[1, 2, 3, 4], [2, 1, 3, 4], [1, 2, 3, 4], [2, 1, 3, 4]]
) == {
    "ok": False,
    "fault": "repeat",
    "row": 3,
}, "rounds partway through a line is a repeat"

assert audit_ringing_line([[1, 2, 3, 4], [2, 1, 3, 4], [1, 2, 3, 4]]) == {
    "ok": True,
    "fault": "",
    "row": 0,
}, "rounds as the last row written is where a line ends"

assert audit_ringing_line([[1, 2]]) == {
    "ok": True,
    "fault": "",
    "row": 0,
}, "a line of rounds alone has nothing to fault"

assert audit_ringing_line([[1, 2, 3, 4], [1, 2, 3]]) == {
    "ok": False,
    "fault": "shape",
    "row": 2,
}, "a row shorter than the opening one is faulted on shape"

assert audit_ringing_line(
    [[1, 2, 3, 4], [2, 1, 3, 4], [2, 1, 4, 3], [4, 2, 1, 3]]
) == {
    "ok": False,
    "fault": "jump",
    "row": 4,
}, "the fault is numbered from the opening row"

assert audit_ringing_line(
    [[1, 2, 3, 4], [2, 1, 4, 3], [2, 4, 1, 3], [1, 2, 3, 4]]
) == {
    "ok": False,
    "fault": "jump",
    "row": 4,
}, "coming round at the end still has to be reached one place at a time"


def rejects(rows):
    try:
        audit_ringing_line(rows)
    except ValueError:
        return True
    return False


assert rejects("1234"), "a rows argument that is not a list is rejected"
assert rejects([]), "an empty rows argument is rejected"
assert rejects([[1, 2], "21"]), "a row that is not a list is rejected"
assert rejects([[1, 2], [2, 1.5]]), "a row entry that is not whole is rejected"
assert rejects([[1]]), "an opening row of one bell is rejected"
assert rejects([[2, 1]]), "an opening row that is not rounds is rejected"
print("ok")
