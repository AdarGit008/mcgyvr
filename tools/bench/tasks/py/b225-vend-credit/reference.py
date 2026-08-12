ACCEPTED = (5, 10, 25, 100)


def vend_credit(coins: list, price: int) -> int:
    if isinstance(price, bool) or not isinstance(price, int) or price < 1 or price % 5:
        raise ValueError("a price is a positive whole number of cents in steps of five")
    credit = 0
    for coin in coins:
        if coin not in ACCEPTED:
            raise ValueError(f"the acceptor spits out {coin}")
        credit += coin
        while credit >= price:
            credit -= price
    return credit
