import re

OFFSET = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHAPE = re.compile(r"[A-G](#|b)?[0-9]")


def shift_note_line(notes: list, shift: int, spelling: str) -> list:
    if not isinstance(notes, list):
        raise ValueError("the notes must be a list")
    if not isinstance(shift, int) or isinstance(shift, bool):
        raise ValueError("the shift must be a whole number")
    if spelling not in ("sharp", "flat"):
        raise ValueError("the spelling is either sharp or flat")
    table = SHARP if spelling == "sharp" else FLAT
    shifted = []
    for note in notes:
        if not isinstance(note, str) or SHAPE.fullmatch(note) is None:
            raise ValueError("a note must be a letter, an optional sign and a digit")
        sign = note[1] if len(note) == 3 else ""
        seat = 12 * int(note[-1]) + OFFSET[note[0]]
        if sign == "#":
            seat += 1
        if sign == "b":
            seat -= 1
        landed = seat + shift
        home = landed // 12
        if home < 0 or home > 9:
            raise ValueError("the shifted note lands outside octaves 0 to 9")
        shifted.append(table[landed % 12] + str(home))
    return shifted
