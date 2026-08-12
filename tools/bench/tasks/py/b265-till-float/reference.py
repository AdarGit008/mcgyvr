def till_float(amount: int, coins: list) -> list:
    counts = []
    left = amount
    for coin in coins:
        counts.append(left // coin)
        left %= coin
    return counts
