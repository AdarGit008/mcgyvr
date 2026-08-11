def cut_roll(length: int, board: list[tuple[int, int]]) -> dict:
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise ValueError("length must be a non-negative whole number")
    order = sorted(board, key=lambda entry: -entry[0])
    best = [0] * (length + 1)
    taken = [0] * (length + 1)
    for metres in range(1, length + 1):
        best[metres] = -1
        for piece, price in order:
            if piece <= metres and price + best[metres - piece] > best[metres]:
                best[metres] = price + best[metres - piece]
                taken[metres] = piece
        if best[metres - 1] > best[metres]:
            best[metres] = best[metres - 1]
            taken[metres] = 0
    pieces = []
    left = length
    while left > 0:
        if taken[left] > 0:
            pieces.append(taken[left])
        left -= taken[left] if taken[left] > 0 else 1
    return {"takings": best[length], "pieces": sorted(pieces, reverse=True)}
