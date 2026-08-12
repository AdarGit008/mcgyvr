def first_over(readings: list, level: int) -> int:
    """The first reading standing above a level, or nothing at all."""
    for reading in readings:
        if reading > level:
            return reading
    return 0
