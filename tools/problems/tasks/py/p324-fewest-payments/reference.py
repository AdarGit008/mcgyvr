def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _person(value):
    return isinstance(value, str) and value != ""


def fewest_payments(dues) -> list:
    if not isinstance(dues, list):
        raise ValueError("the dues must be a list")
    position = {}
    for due in dues:
        if not isinstance(due, list) or len(due) != 3:
            raise ValueError("a due must be a list of exactly three items")
        payer, payee, amount = due
        if not _person(payer) or not _person(payee):
            raise ValueError("a name must be a non-empty string")
        if payer == payee:
            raise ValueError("a due must not put one person on both sides")
        if not _whole(amount) or amount < 1:
            raise ValueError("an amount must be a whole number of one or more")
        position[payer] = position.get(payer, 0) - amount
        position[payee] = position.get(payee, 0) + amount

    red = {name: -net for name, net in position.items() if net < 0}
    black = {name: net for name, net in position.items() if net > 0}

    payments = []
    while red:
        red_names = sorted(red)
        black_names = sorted(black)
        payer = ""
        payee = ""
        for name in red_names:
            for other in black_names:
                if red[name] == black[other]:
                    payer = name
                    payee = other
                    break
            if payer != "":
                break
        if payer == "":
            for name in red_names:
                if payer == "" or red[name] > red[payer]:
                    payer = name
            for other in black_names:
                if payee == "" or black[other] > black[payee]:
                    payee = other
        moved = min(red[payer], black[payee])
        payments.append([payer, payee, moved])
        red[payer] -= moved
        if red[payer] == 0:
            del red[payer]
        black[payee] -= moved
        if black[payee] == 0:
            del black[payee]
    return payments
