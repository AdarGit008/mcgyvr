def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def trace_uneven_payoff(opening: int, rate: int, instalments: object) -> list[list[int]]:
    if not _whole(opening) or not _whole(rate):
        raise ValueError("opening and rate must be whole numbers")
    if opening <= 0:
        raise ValueError("opening must be above zero")
    if rate < 0:
        raise ValueError("rate must not fall below zero")
    if not isinstance(instalments, list) or not instalments:
        raise ValueError("instalments must be a non-empty list")
    for paid in instalments:
        if not _whole(paid) or paid < 0:
            raise ValueError("every instalment must be a whole number of cents, not below zero")

    rows: list[list[int]] = []
    principal = opening
    pile = 0
    for paid in instalments:
        levy = (principal * rate + 5000) // 10000
        if paid > pile + levy + principal:
            raise ValueError("an instalment may not exceed everything then owed")
        left = paid
        to_pile = min(left, pile)
        pile -= to_pile
        left -= to_pile
        to_levy = min(left, levy)
        left -= to_levy
        pile += levy - to_levy
        to_principal = left
        principal -= to_principal
        rows.append([paid, levy, to_pile + to_levy, to_principal, principal, pile])
    if principal > 0 or pile > 0:
        rows.append([pile + principal, 0, pile, principal, 0, 0])
    return rows
