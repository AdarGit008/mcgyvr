import re

STEPS = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
)
LOWER = re.compile(r"^[a-z]+$")


def key_row_suggestions(
    rows: list[str], typed: str, lexicon: list[str]
) -> list[str]:
    if not isinstance(rows, list) or len(rows) == 0:
        raise ValueError("the drawing must be a non-empty list of rows")
    spot_of: dict[str, tuple[int, int]] = {}
    for r, row in enumerate(rows):
        if not isinstance(row, str) or row == "":
            raise ValueError("every row must be a non-empty string")
        if LOWER.match(row) is None:
            raise ValueError("a row may hold only lowercase letters")
        for c, letter in enumerate(row):
            if letter in spot_of:
                raise ValueError("a letter is drawn twice")
            spot_of[letter] = (r, c)
    if not isinstance(typed, str) or LOWER.match(typed) is None:
        raise ValueError("the typed word must be a non-empty lowercase string")
    for letter in typed:
        if letter not in spot_of:
            raise ValueError("a typed letter is nowhere on the drawing")
    if not isinstance(lexicon, list):
        raise ValueError("the accepted list must be a list")
    for entry in lexicon:
        if not isinstance(entry, str) or LOWER.match(entry) is None:
            raise ValueError("every accepted word must be a non-empty lowercase string")

    accepted = set(lexicon)
    if typed in accepted:
        return []
    found = []
    for place, letter in enumerate(typed):
        r0, c0 = spot_of[letter]
        for step, (dr, dc) in enumerate(STEPS):
            r = r0 + dr
            c = c0 + dc
            if r < 0 or r >= len(rows) or c < 0 or c >= len(rows[r]):
                continue
            word = typed[:place] + rows[r][c] + typed[place + 1 :]
            if word in accepted:
                found.append((step, place, word))
    found.sort()
    return [word for _, _, word in found]
