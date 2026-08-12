def rate_cap(price: int, rate: int, most: int) -> int:
    rise = price * rate // 100
    if rise > most:
        rise = most
    return price + rise
