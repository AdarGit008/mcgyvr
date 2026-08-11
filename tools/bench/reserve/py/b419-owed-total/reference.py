def owed_total(entries: list) -> int:
    """What is owed across a ledger of charges and payments."""
    total = 0
    for entry in entries:
        total += entry
    if total < 0:
        raise ValueError("the total cannot fall below nothing")
    return total
