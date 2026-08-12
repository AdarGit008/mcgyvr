def fuel_legs(litres: int, burn: int) -> int:
    if burn <= 0:
        raise ValueError("burn must be positive")
    legs = 0
    while litres >= burn:
        litres -= burn
        legs += 1
    return legs
