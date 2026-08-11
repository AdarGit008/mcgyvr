def interest_add(amount: int, rate: int, years: int) -> int:
    interest = amount * rate * years // 100
    return amount + interest
