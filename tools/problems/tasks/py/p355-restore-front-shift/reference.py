def restore_front_shift(alphabet: str, codes: list) -> str:
    if not isinstance(alphabet, str):
        raise ValueError("the alphabet must be a string")
    if len(alphabet) == 0:
        raise ValueError("the alphabet must not be empty")
    ring = list(alphabet)
    if len(set(ring)) != len(ring):
        raise ValueError("the alphabet carries one character twice")
    if not isinstance(codes, list):
        raise ValueError("the codes must be a list")
    pieces = []
    for code in codes:
        if not isinstance(code, int) or isinstance(code, bool):
            raise ValueError("every code must be a whole number")
        if code < 0 or code >= len(ring):
            raise ValueError("the code names no slot of the ring")
        character = ring[code]
        pieces.append(character)
        ring.pop(code)
        ring.insert(0, character)
    return "".join(pieces)
