def days_for(size: int, rate: int) -> int:
    if rate <= 0:
        raise ValueError("a rate must be positive")
    return (size + rate - 1) // rate


def plan_days(sizes: list, rate: int) -> list:
    return [days_for(size, rate) for size in sizes]
