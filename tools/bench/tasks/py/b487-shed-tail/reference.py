def shed_tail(text: str, piece: str) -> str:
    if len(piece) == 0:
        return text
    left = text
    while left.endswith(piece):
        left = left[: len(left) - len(piece)]
    return left
