def fit_budget(prices: list, budget: int) -> int:
    if budget < 0:
        raise ValueError("budget cannot be negative")
    bought = 0
    left = budget
    for price in sorted(prices):
        if price > left:
            break
        left -= price
        bought += 1
    return bought
