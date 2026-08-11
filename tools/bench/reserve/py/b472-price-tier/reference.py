def tier_rate(units: int) -> int:
    if units < 10:
        return 50
    if units < 50:
        return 40
    return 30


def tier_cost(units: int) -> int:
    """The whole charge in cents for a count of units."""
    if units == 0:
        return 0
    gross = units * tier_rate(units)
    if gross < 100:
        return 100
    return gross
