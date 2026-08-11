def flip_one(pair: list) -> list:
    return [pair[1], pair[0]]


def flip_all(pairs: list) -> list:
    flipped = []
    for pair in pairs:
        flipped.append(flip_one(pair))
    return flipped
