def first_clue_clash(line: str, clues: list) -> int:
    if not isinstance(line, str) or not line:
        raise ValueError("the line must be a non-empty string")
    for cell in line:
        if cell not in ("#", "."):
            raise ValueError("unusable cell: " + cell)
    if not isinstance(clues, list):
        raise ValueError("clues must be a list")
    for clue in clues:
        if not isinstance(clue, int) or isinstance(clue, bool) or clue < 1:
            raise ValueError("every clue must be a whole number above zero")
    needed = sum(clues) + (len(clues) - 1 if clues else 0)
    if needed > len(line):
        raise ValueError("the clues cannot fit on a line this short")

    runs = []
    held = 0
    for cell in line:
        if cell == "#":
            held += 1
        elif held > 0:
            runs.append(held)
            held = 0
    if held > 0:
        runs.append(held)

    for place in range(max(len(runs), len(clues))):
        if place >= len(runs) or place >= len(clues):
            return place
        if runs[place] != clues[place]:
            return place
    return -1
