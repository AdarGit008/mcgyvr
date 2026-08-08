import re

LADDER = ["C", "D", "E", "F", "G", "A", "B"]
OFFSETS = [0, 2, 4, 5, 7, 9, 11]
NOTE = re.compile(r"[A-G](##|#|bb|b)?[0-9]")
STAMP = re.compile(r"[A-G](#|b)")
SIGNS = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}


def _worth(run):
    if run == "":
        return 0
    return len(run) if run[0] == "#" else -len(run)


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def transpose_note_run(notes: list, rung: int, size: int, key: list) -> list:
    if not isinstance(notes, list):
        raise ValueError("the notes must be a list")
    if not _whole(rung) or not _whole(size):
        raise ValueError("the rung and the size must be whole numbers")
    if not isinstance(key, list):
        raise ValueError("the key must be a list")
    stamps = {}
    for stamp in key:
        if not isinstance(stamp, str) or STAMP.fullmatch(stamp) is None:
            raise ValueError("a stamp is a letter with exactly one sign")
        if stamp[0] in stamps:
            raise ValueError("a letter is stamped twice")
        stamps[stamp[0]] = _worth(stamp[1])

    moved = []
    for note in notes:
        if not isinstance(note, str) or NOTE.fullmatch(note) is None:
            raise ValueError("a note is a letter, up to two signs and a digit")
        letter = note[0]
        run = note[1:-1]
        octave = int(note[-1])
        worth = stamps.get(letter, 0) if run == "" else _worth(run)
        place = LADDER.index(letter)
        pitch = 12 * octave + OFFSETS[place] + worth

        walked = place + rung
        home = octave + walked // 7
        if home < 0 or home > 9:
            raise ValueError("the moved note falls outside octaves 0 to 9")
        landed = walked % 7
        bare = 12 * home + OFFSETS[landed]
        needed = pitch + size - bare
        if needed < -2 or needed > 2:
            raise ValueError("the moved note would need more than two signs")
        moved.append(LADDER[landed] + SIGNS[needed] + str(home))
    return moved
