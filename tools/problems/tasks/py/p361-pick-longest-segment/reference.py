VALUES = {"W": 0, "X": 1, "Y": 2, "Z": 3}
RESIDUES = "abcdefghijklmnop"
OPENER = "ZWX"
HALTS = ("ZZW", "ZZX")


def pick_longest_segment(strand: str) -> dict:
    if not isinstance(strand, str):
        raise ValueError("the strand must be a string")
    if len(strand) == 0:
        raise ValueError("the strand must not be empty")
    for symbol in strand:
        if symbol not in VALUES:
            raise ValueError("the strand holds a symbol outside W, X, Y and Z")
    best = None
    for frame in (0, 1, 2):
        codons = []
        place = frame
        while place + 3 <= len(strand):
            codons.append((place, strand[place : place + 3]))
            place += 3
        for opening, (start, codon) in enumerate(codons):
            if codon != OPENER:
                continue
            letters = [RESIDUES[4 * VALUES[OPENER[0]] + VALUES[OPENER[1]]]]
            complete = False
            for onward in range(opening + 1, len(codons)):
                later = codons[onward][1]
                if later in HALTS:
                    complete = True
                    break
                letters.append(RESIDUES[4 * VALUES[later[0]] + VALUES[later[1]]])
            if not complete:
                continue
            residues = "".join(letters)
            ranking = (-len(residues), frame, start)
            if best is None or ranking < best[0]:
                best = (ranking, frame, start, residues)
    if best is None:
        return {"frame": -1, "start": -1, "residues": ""}
    return {"frame": best[1], "start": best[2], "residues": best[3]}
