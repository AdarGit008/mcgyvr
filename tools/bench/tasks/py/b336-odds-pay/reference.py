def payout(stake: int, odds: int) -> int:
    if stake < 0:
        raise ValueError("a stake cannot be negative")
    return stake * odds


def settle_all(bets: list) -> int:
    total = 0
    for bet in bets:
        if bet["won"]:
            total += payout(bet["stake"], bet["odds"])
    return total
