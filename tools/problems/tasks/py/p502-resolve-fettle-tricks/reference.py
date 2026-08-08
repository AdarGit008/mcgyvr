import re

CARD = re.compile(r"[bcfl](?:[1-9]|1[0-3])")
CARRIES = {10: 1, 11: 2, 12: 3, 13: 4, 1: 5}


def _height(strength: int) -> int:
    return 14 if strength == 1 else strength


def resolve_fettle_tricks(deal: dict) -> dict:
    if not isinstance(deal, dict):
        raise ValueError("the deal must be a mapping")
    trump = deal.get("trump")
    if not isinstance(trump, str) or trump not in ("b", "c", "f", "l", "none"):
        raise ValueError("trump must be a house letter or the word none")
    tricks = deal.get("tricks")
    if not isinstance(tricks, list) or not tricks:
        raise ValueError("tricks must be a non-empty list")

    laid = set()
    parsed = []
    for trick in tricks:
        if not isinstance(trick, list) or len(trick) != 4:
            raise ValueError("a trick must be a list of exactly four cards")
        row = []
        for card in trick:
            if not isinstance(card, str) or CARD.fullmatch(card) is None:
                raise ValueError("a card must be a house letter and a strength from 1 to 13")
            if card in laid:
                raise ValueError("a card is laid twice in the deal")
            laid.add(card)
            row.append((card[0], int(card[1:])))
        parsed.append(row)

    takers = []
    worths = []
    banked = [0, 0, 0, 0]
    leader = 0
    for index, row in enumerate(parsed):
        called = row[0][0]
        wanted = trump if trump != "none" and any(h == trump for h, _ in row) else called
        best = 0
        for place in range(1, 4):
            if row[place][0] != wanted:
                continue
            if row[best][0] != wanted or _height(row[place][1]) > _height(row[best][1]):
                best = place
        worth = sum(CARRIES.get(strength, 0) for _, strength in row)
        if index == len(parsed) - 1:
            worth += 3
        taker = (leader + best) % 4
        takers.append(taker)
        worths.append(worth)
        banked[taker] += worth
        leader = taker

    return {
        "takers": takers,
        "worths": worths,
        "even": banked[0] + banked[2],
        "odd": banked[1] + banked[3],
    }
