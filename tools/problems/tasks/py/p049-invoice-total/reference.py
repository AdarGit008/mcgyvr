def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _half_up(amount: int, bps: int) -> int:
    return (amount * bps + 5000) // 10000


def invoice_total(lines: list[dict], rate: int) -> dict[str, int]:
    if not isinstance(lines, list) or not lines:
        raise ValueError("an invoice needs at least one line")
    if not _whole(rate) or rate < 0 or rate > 10000:
        raise ValueError("tax rate must be an integer in 0..10000 basis points")
    subtotal = 0
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("line must be a record")
        qty = line.get("qty")
        unit = line.get("unit")
        discount = line.get("discount")
        if not _whole(qty) or qty <= 0:
            raise ValueError("qty must be a positive integer")
        if not _whole(unit) or unit < 0:
            raise ValueError("unit must be a non-negative integer of cents")
        if not _whole(discount) or discount < 0 or discount > 10000:
            raise ValueError("discount must be an integer in 0..10000 basis points")
        gross = qty * unit
        subtotal += gross - _half_up(gross, discount)
    tax = _half_up(subtotal, rate)
    return {"subtotal": subtotal, "tax": tax, "total": subtotal + tax}
