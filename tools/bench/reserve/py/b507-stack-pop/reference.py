def stack_pop(orders: list[str]) -> list[str]:
    pile = []
    for order in orders:
        if order == "take":
            if len(pile) == 0:
                raise ValueError("there is nothing left to take")
            pile.pop()
        else:
            pile.append(order)
    return pile
