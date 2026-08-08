def shelf_count(entries: list) -> list:
    """Fold shelf entries into a final count and a skipped-take tally."""
    count = 0
    skipped = 0
    for kind, amount in entries:
        if kind not in ("add", "take", "fix"):
            raise ValueError("unknown kind")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError("amount must be a non-negative integer")
        if kind == "add":
            count += amount
        elif kind == "fix":
            count = amount
        elif amount > count:
            skipped += 1
        else:
            count -= amount
    return [count, skipped]
