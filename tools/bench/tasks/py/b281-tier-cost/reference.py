def tier_cost(units: int, allowance: int, first_rate: int, later_rate: int) -> int:
    if units < 0:
        raise ValueError("units cannot be negative")
    if units <= allowance:
        return units * first_rate
    return allowance * first_rate + (units - allowance) * later_rate
