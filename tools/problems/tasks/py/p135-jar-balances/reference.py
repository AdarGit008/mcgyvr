def jar_balances(topup, lid, outflows):
    if not isinstance(topup, int) or isinstance(topup, bool) or topup < 0:
        raise ValueError("topup must be a non-negative integer")
    if not isinstance(lid, int) or isinstance(lid, bool) or lid < 0:
        raise ValueError("lid must be a non-negative integer")
    if not isinstance(outflows, list):
        raise ValueError("outflows must be a list")
    closes = []
    held = 0
    for outflow in outflows:
        if not isinstance(outflow, int) or isinstance(outflow, bool) or outflow < 0:
            raise ValueError("an outflow must be a non-negative integer")
        held += topup
        if outflow > held:
            raise ValueError("the jar cannot cover this outflow")
        held -= outflow
        if held > lid:
            held = lid
        closes.append(held)
    return closes
