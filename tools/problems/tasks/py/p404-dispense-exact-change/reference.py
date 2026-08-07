def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_hopper(hopper):
    if not isinstance(hopper, list) or not hopper:
        raise ValueError("the hopper must list at least one face")
    seen = set()
    faces = []
    for row in hopper:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("each hopper entry is a face and a stock")
        face, stock = row
        if not _whole(face) or face < 1:
            raise ValueError("a face value must be a whole number above nothing")
        if not _whole(stock) or stock < 0:
            raise ValueError("a stock must be a whole number of nothing or more")
        if face in seen:
            raise ValueError("face {} is listed twice".format(face))
        seen.add(face)
        faces.append((face, stock))
    faces.sort(key=lambda pair: -pair[0])
    return faces


def dispense_exact_change(amount: int, hopper: list) -> list:
    if not _whole(amount) or amount < 0 or amount > 100000:
        raise ValueError("the amount must be a whole number of 0 through 100000")
    faces = _read_hopper(hopper)
    unreachable = amount + 1
    deeper = [unreachable] * (amount + 1)
    deeper[0] = 0
    taken = [None] * len(faces)
    for index in range(len(faces) - 1, -1, -1):
        face, stock = faces[index]
        level = [unreachable] * (amount + 1)
        picks = [0] * (amount + 1)
        for rest in range(amount + 1):
            fewest = unreachable
            best = 0
            limit = min(stock, rest // face)
            for count in range(limit + 1):
                below = deeper[rest - count * face]
                if below == unreachable:
                    continue
                coins = below + count
                if coins < fewest or (coins == fewest and count > best):
                    fewest = coins
                    best = count
            level[rest] = fewest
            picks[rest] = best
        taken[index] = picks
        deeper = level
    if deeper[amount] == unreachable:
        raise ValueError("the hopper cannot pay {} exactly".format(amount))
    payout = []
    rest = amount
    for index, (face, _stock) in enumerate(faces):
        count = taken[index][rest]
        if count > 0:
            payout.append([face, count])
        rest -= count * face
    return payout
