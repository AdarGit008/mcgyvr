"""Deal a deck's cards round-robin into a fixed number of piles."""


def deal_rounds(deck: str, hands: int) -> list:
    if not isinstance(deck, str):
        raise ValueError("deal_rounds expects a string deck")
    if isinstance(hands, bool) or not isinstance(hands, int) or hands < 1:
        raise ValueError("hands must be a whole number of at least one")
    piles = [""] * hands
    for index, card in enumerate(deck):
        piles[index % hands] += card
    return piles
