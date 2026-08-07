def grade_bars(line: str, beats: int, unit: int) -> list:
    if not isinstance(line, str):
        raise ValueError("line must be a string")
    if not isinstance(beats, int) or isinstance(beats, bool) or beats < 1:
        raise ValueError("beats must be a whole number of at least one")
    if unit not in (1, 2, 4, 8, 16):
        raise ValueError("unit must be 1, 2, 4, 8 or 16")

    worth = {"w": 64, "h": 32, "q": 16, "e": 8, "s": 4}
    holds = beats * 64 // unit
    verdicts = []
    for bar in line.split("|"):
        notes = [piece for piece in bar.split(" ") if piece]
        if not notes:
            raise ValueError("a bar holds no notes at all")
        filled = 0
        for note in notes:
            letter = note[0]
            if letter not in worth:
                raise ValueError("unknown note letter " + letter)
            tail = note[1:]
            if tail not in ("", "."):
                raise ValueError("a note may carry at most one full stop")
            plain = worth[letter]
            filled += plain + plain // 2 if tail == "." else plain
        if filled < holds:
            verdicts.append("short")
        elif filled > holds:
            verdicts.append("long")
        else:
            verdicts.append("exact")
    return verdicts
