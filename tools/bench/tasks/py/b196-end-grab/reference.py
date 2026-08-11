"""Play a row of cards out to the last card, each turn grabbing the better end."""


def end_grab(cards: list) -> dict:
    row = list(cards)
    taken = []
    totals = [0, 0]
    turn = 0
    while row:
        if row[0] >= row[-1]:
            card = row.pop(0)
        else:
            card = row.pop()
        taken.append(card)
        totals[turn] += card
        turn = 1 - turn
    return {"first": totals[0], "second": totals[1], "taken": taken}
