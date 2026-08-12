def quarter_hour(minutes: int) -> int:
    if minutes < 0:
        raise ValueError("minutes cannot be negative")
    quarters = minutes // 15
    return quarters * 15
