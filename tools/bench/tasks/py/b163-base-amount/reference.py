def base_amount(amount: int, unit: str, defs: dict, base: str) -> int:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError("amount must be a non-negative integer")

    def unwind(count, name, depth):
        if name == base:
            return count
        if depth > len(defs) or name not in defs:
            raise ValueError("unit is unknown or its chain never reaches the base")
        factor, finer = defs[name]
        if isinstance(factor, bool) or not isinstance(factor, int) or factor < 1:
            raise ValueError("factor must be a positive integer")
        return unwind(count * factor, finer, depth + 1)

    return unwind(amount, unit, 0)
