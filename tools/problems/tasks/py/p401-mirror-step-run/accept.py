from solution import mirror_step_run

assert mirror_step_run(1) == {
    "words": ["0", "1"],
    "flips": [1],
}, "one mark makes a two-word turn"

assert mirror_step_run(2) == {
    "words": ["00", "01", "11", "10"],
    "flips": [2, 1, 2],
}, "two marks: the second writing comes back in reverse"

assert mirror_step_run(3) == {
    "words": ["000", "001", "011", "010", "110", "111", "101", "100"],
    "flips": [3, 2, 3, 1, 3, 2, 3],
}, "three marks, with the leading column flipping once at the halfway notch"

four = mirror_step_run(4)
assert len(four["words"]) == 16, "four marks make sixteen words"
assert four["words"][0] == "0000", "the turn opens with all marks clear"
assert four["words"][15] == "1000", "and closes one mark away from the start"
assert four["flips"] == [
    4,
    3,
    4,
    2,
    4,
    3,
    4,
    1,
    4,
    3,
    4,
    2,
    4,
    3,
    4,
], "the flip columns fall into the ruler pattern"

five = mirror_step_run(5)
sound = len(five["words"]) == 32 and len(five["flips"]) == 31
sound = sound and len(set(five["words"])) == 32
for index in range(1, len(five["words"])):
    if not sound:
        break
    before = five["words"][index - 1]
    after = five["words"][index]
    altered = [
        column + 1 for column in range(5) if before[column] != after[column]
    ]
    sound = len(altered) == 1 and altered[0] == five["flips"][index - 1]
assert sound, "every notch of a five-mark turn alters the named column only"

twelve = mirror_step_run(12)
assert len(twelve["words"]) == 4096, "twelve marks make four thousand words"
assert len(set(twelve["words"])) == 4096, "and no word repeats"
assert len(twelve["flips"]) == 4095, "one flip fewer than there are words"
assert twelve["words"][0] == "0" * 12, "opening word of the long turn"
assert twelve["words"][4095] == "1" + "0" * 11, "closing word of the long turn"


def rejects(value):
    try:
        mirror_step_run(value)
    except ValueError:
        return True
    return False


assert rejects(0), "a width of nothing is rejected"
assert rejects(13), "a width past twelve is rejected"
assert rejects(2.5), "a fractional width is rejected"
assert rejects("3"), "text is not a width"
assert rejects(None), "nothing at all is rejected"
print("ok")
