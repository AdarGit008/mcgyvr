from solution import shift_note_line

assert shift_note_line(["C4", "E4", "G4"], 2, "sharp") == ["D4", "F#4", "A4"], (
    "a whole tone up under the sharp table"
)
assert shift_note_line(["C4", "E4", "G4"], 2, "flat") == ["D4", "Gb4", "A4"], (
    "the same shift spelled the other way"
)
assert shift_note_line(["B3"], 1, "sharp") == ["C4"], (
    "a step past B climbs into the next octave"
)
assert shift_note_line(["C4"], -1, "flat") == ["B3"], (
    "a step below C falls into the octave beneath"
)
assert shift_note_line(["F#3"], 3, "flat") == ["A3"], (
    "a raised note reads its sign before the shift"
)
assert shift_note_line(["Eb5"], -2, "flat") == ["Db5"], (
    "a lowered note shifted downwards"
)
assert shift_note_line(["Cb4"], 0, "sharp") == ["B3"], (
    "a lowered C already sits in the octave below"
)
assert shift_note_line(["B#4"], 0, "flat") == ["C5"], (
    "a raised B already sits in the octave above"
)
assert shift_note_line(["D4"], 0, "sharp") == ["D4"], (
    "a shift of nothing still respells nothing"
)
assert shift_note_line(["C4"], 12, "sharp") == ["C5"], (
    "twelve half tones is one whole octave"
)
assert shift_note_line(["A0", "C1"], -1, "sharp") == ["G#0", "B0"], (
    "the lowest octave is reachable from above"
)
assert shift_note_line([], 5, "flat") == [], "no notes shift to no notes"


def rejects(one, two, three):
    try:
        shift_note_line(one, two, three)
    except ValueError:
        return True
    return False


assert rejects("C4", 1, "sharp"), "notes given as a string is rejected"
assert rejects(["H4"], 1, "sharp"), "a letter past G is rejected"
assert rejects(["C"], 1, "sharp"), "a note without an octave is rejected"
assert rejects(["C##4"], 1, "sharp"), "two signs at once are rejected"
assert rejects(["c4"], 1, "sharp"), "a small letter is rejected"
assert rejects(["C4"], 1.5, "sharp"), "a fractional shift is rejected"
assert rejects(["C4"], True, "sharp"), "a shift given as a boolean is rejected"
assert rejects(["C4"], 1, "wide"), "a spelling outside the two words is rejected"
assert rejects(["C0"], -1, "sharp"), "falling below octave zero is rejected"
assert rejects(["B9"], 1, "sharp"), "climbing past octave nine is rejected"
print("ok")
