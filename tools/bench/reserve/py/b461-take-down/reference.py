def take_down(held: int, amount: int) -> int:
    """What is left after an amount is taken from stock."""
    if amount > held:
        raise ValueError("more than is held cannot be taken")
    return held - amount
