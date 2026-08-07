import re

HOUSE_WEIGHT = {"m": 4, "r": 3, "s": 2, "v": 1}
STRENGTH = {
    "monolith": 5,
    "prism": 4,
    "chain": 3,
    "echo": 2,
    "twin": 1,
    "drift": 0,
}
CARD = re.compile(r"(10|[1-9])([mrsv])")


def order_skein_hands(hands: list) -> dict:
    if not isinstance(hands, list) or not hands:
        raise ValueError("the argument must be a list holding at least one hand")
    graded = []
    for at, hand in enumerate(hands):
        if not isinstance(hand, list) or len(hand) != 5:
            raise ValueError("a hand must be a list of exactly five cards")
        pips = []
        weights = []
        houses = set()
        written = set()
        for card in hand:
            match = CARD.fullmatch(card) if isinstance(card, str) else None
            if match is None:
                raise ValueError("a card must be a pip from 1 to 10 and one house letter")
            if card in written:
                raise ValueError("a hand writes the same card twice")
            written.add(card)
            pips.append(int(match.group(1)))
            weights.append(HOUSE_WEIGHT[match.group(2)])
            houses.add(match.group(2))
        carried = {}
        for pip in pips:
            carried[pip] = carried.get(pip, 0) + 1
        ladder = sorted(carried, key=lambda pip: (-carried[pip], -pip))
        span = max(pips) - min(pips)
        grade = "drift"
        if len(ladder) == 2:
            grade = "monolith"
        elif len(ladder) == 5 and len(houses) == 4:
            grade = "prism"
        elif len(ladder) == 5 and span == 4:
            grade = "chain"
        elif len(ladder) == 3:
            grade = "echo"
        elif len(ladder) == 4:
            grade = "twin"
        graded.append(
            {
                "grade": grade,
                "ladder": ladder,
                "weights": sorted(weights, reverse=True),
                "at": at,
            }
        )
    ranked = sorted(
        graded,
        key=lambda entry: (
            -STRENGTH[entry["grade"]],
            [-pip for pip in entry["ladder"]],
            [-weight for weight in entry["weights"]],
            entry["at"],
        ),
    )
    return {
        "grades": [entry["grade"] for entry in graded],
        "order": [entry["at"] for entry in ranked],
    }
