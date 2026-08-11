import math


def scale_batch(amounts: list, factor: float) -> list:
    if factor < 0:
        raise ValueError("factor cannot be negative")
    scaled = []
    for amount in amounts:
        scaled.append(math.ceil(amount * factor))
    return scaled
