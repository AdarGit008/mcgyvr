import re

CARD = re.compile(r"([ghjk])([1-8])")


def name_kettle_hands(hands: list) -> dict:
    if not isinstance(hands, list) or not hands:
        raise ValueError("the argument must be a list holding at least one hand")
    names = []
    totals = []
    for hand in hands:
        if not isinstance(hand, list) or len(hand) != 4:
            raise ValueError("a hand must be a list of exactly four cards")
        heats = []
        flues = []
        written = set()
        for card in hand:
            match = CARD.fullmatch(card) if isinstance(card, str) else None
            if match is None:
                raise ValueError("a card must be one flue letter and one heat from 1 to 8")
            if card in written:
                raise ValueError("a card is written twice inside a hand")
            written.add(card)
            flues.append(match.group(1))
            heats.append(int(match.group(2)))
        total = sum(heats)
        spread = max(heats) - min(heats)
        flue_count = {}
        for flue in flues:
            flue_count[flue] = flue_count.get(flue, 0) + 1
        two_each = len(flue_count) == 2 and all(
            count == 2 for count in flue_count.values()
        )
        if spread == 3 and len(set(heats)) == 4 and len(flue_count) == 4:
            name = "kiln-run"
        elif two_each:
            name = "double-flue"
        elif total % 7 == 0:
            name = "banked"
        elif spread >= 6:
            name = "draught"
        else:
            name = "cold"
        names.append(name)
        totals.append(total)
    return {"names": names, "totals": totals}
