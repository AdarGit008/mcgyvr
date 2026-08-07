MARKER = "|"


def _rank_of(symbol: str) -> int:
    if symbol == MARKER:
        return 0
    if symbol == " ":
        return 1
    return ord(symbol) - 95


def fold_ribbon_rotations(ribbon: str) -> dict:
    if not isinstance(ribbon, str):
        raise ValueError("the ribbon must be a string")
    if len(ribbon) == 0:
        raise ValueError("the ribbon must not be empty")
    if MARKER in ribbon:
        raise ValueError("the ribbon must not already carry the marker")
    for symbol in ribbon:
        if not ("a" <= symbol <= "z") and symbol != " ":
            raise ValueError("the ribbon holds a symbol outside lowercase and space")
    glued = ribbon + MARKER
    width = len(glued)

    def key(start: int) -> list:
        return [_rank_of(glued[(start + step) % width]) for step in range(width)]

    turns = sorted(range(width), key=key)
    line = "".join(glued[(start + width - 1) % width] for start in turns)
    return {"line": line, "home": turns.index(0)}
