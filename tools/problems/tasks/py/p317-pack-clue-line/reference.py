"""The clue's groups crowded as far to the left as they will go."""


def pack_clue_line(width: int, clues: list) -> str:
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError("the width must be a whole number above zero")
    if not isinstance(clues, list):
        raise ValueError("clues must be a list")
    for clue in clues:
        if not isinstance(clue, int) or isinstance(clue, bool) or clue < 1:
            raise ValueError("every clue must be a whole number above zero")
    needed = sum(clues) + (len(clues) - 1 if clues else 0)
    if needed > width:
        raise ValueError("the clues cannot be drawn within this width")
    drawn = ".".join("#" * clue for clue in clues)
    return drawn + "." * (width - len(drawn))
