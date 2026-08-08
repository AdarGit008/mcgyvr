def accrue_flat_interest(
    principal_cents: int,
    rate_basis_points: int,
    days: int,
    year_basis: int,
) -> int:
    for value in (principal_cents, rate_basis_points, days, year_basis):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("every argument must be a whole number")
    if principal_cents < 0 or rate_basis_points < 0 or days < 0:
        raise ValueError("principal, rate and day count must not be below zero")
    if year_basis not in (360, 365):
        raise ValueError("the year basis must be 360 or 365")
    product = principal_cents * rate_basis_points * days
    divisor = 10000 * year_basis
    return (2 * product + divisor) // (2 * divisor)
