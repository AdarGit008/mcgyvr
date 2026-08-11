def shuffle_deal(cards: list, hands: int) -> list:
    if hands == 0:
        return []
    dealt = [[] for _ in range(hands)]
    for i, card in enumerate(cards):
        dealt[i % hands].append(card)
    return dealt


def deal_counts(dealt: list) -> list:
    return [len(hand) for hand in dealt]
