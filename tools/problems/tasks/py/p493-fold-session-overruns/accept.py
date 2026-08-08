from solution import fold_session_overruns


def turn(speaker, slot, ran, pause):
    return {"speaker": speaker, "slot": slot, "ran": ran, "pause": pause}


assert fold_session_overruns(
    [turn("ines", 20, 35, 10), turn("omar", 15, 15, 5), turn("pia", 10, 20, 0)], 60
) == {
    "lines": ["ines 0 35 full", "omar 35 50 full", "pia 55 60 cut"],
    "spill": [],
    "finish": 60,
}, "a squeezed break stops at nought and the last turn is guillotined"

assert fold_session_overruns(
    [turn("kai", 30, 30, 0), turn("lena", 10, 10, 0)], 30
) == {
    "lines": ["kai 0 30 full"],
    "spill": ["lena"],
    "finish": 30,
}, "a turn beginning exactly on the wall never happens"

assert fold_session_overruns(
    [turn("a", 10, 25, 0), turn("b", 5, 5, 0), turn("c", 5, 5, 0)], 20
) == {
    "lines": ["a 0 20 cut"],
    "spill": ["b", "c"],
    "finish": 20,
}, "everything behind a guillotined turn spills"

assert fold_session_overruns([], 45) == {
    "lines": [],
    "spill": [],
    "finish": 0,
}, "an empty runsheet closes at nought"

assert fold_session_overruns([turn("x", 20, 12, 8), turn("y", 10, 10, 0)], 100) == {
    "lines": ["x 0 12 full", "y 20 30 full"],
    "spill": [],
    "finish": 30,
}, "a speaker inside the slot leaves the printed break whole"

assert fold_session_overruns([turn("p", 10, 13, 8), turn("q", 5, 5, 0)], 100) == {
    "lines": ["p 0 13 full", "q 18 23 full"],
    "spill": [],
    "finish": 23,
}, "a small overrun squeezes part of the break"

assert fold_session_overruns([turn("solo", 5, 0, 3)], 12) == {
    "lines": ["solo 0 0 full"],
    "spill": [],
    "finish": 0,
}, "a speaker who uses no minutes still holds the lectern"


def rejects(*args):
    try:
        fold_session_overruns(*args)
    except ValueError:
        return True
    return False


assert rejects("nope", 10), "runsheet must be a list"
assert rejects([7], 10), "an entry must be a record"
assert rejects([{"speaker": "z", "slot": 5, "ran": 5}], 10), "a missing key is refused"
assert rejects([turn("", 5, 5, 0)], 10), "an empty speaker is refused"
assert rejects([turn("z", 5, 5, 0), turn("z", 4, 4, 0)], 10), "a repeated speaker is refused"
assert rejects([turn("z", 0, 5, 0)], 10), "a slot of nought is refused"
assert rejects([turn("z", 5, -1, 0)], 10), "a negative ran is refused"
assert rejects([turn("z", 5, 5, -3)], 10), "a negative pause is refused"
assert rejects([turn("z", 5, 5, 0)], 0), "a wall of nought is refused"
print("ok")
