def weigh_in(grams: int) -> list:
    if grams < 0:
        raise ValueError("weight cannot be negative")
    kilos = grams // 1000
    left = grams - kilos * 1000
    return [kilos, left]
