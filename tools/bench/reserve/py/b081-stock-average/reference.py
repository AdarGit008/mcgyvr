"""One warehouse item's stockbook under moving-average costing."""


def receipt_cents(qty, unit_cents):
    if not isinstance(qty, int) or qty <= 0:
        raise ValueError("receive quantity must be a positive integer")
    if not isinstance(unit_cents, int) or unit_cents < 0:
        raise ValueError("unit cost must be a non-negative integer of cents")
    return qty * unit_cents


def run_stockbook(moves):
    held = 0
    worth = 0
    issued = 0
    for move in moves:
        if move[0] == "receive":
            qty = move[1]
            worth += receipt_cents(qty, move[2])
            held += qty
        elif move[0] == "issue":
            qty = move[1]
            if not isinstance(qty, int) or qty <= 0:
                raise ValueError("issue quantity must be a positive integer")
            if qty > held:
                raise ValueError("issue exceeds the stock held")
            relief = worth * qty // held
            worth -= relief
            issued += relief
            held -= qty
    return {"held": held, "worth": worth, "issued": issued}
