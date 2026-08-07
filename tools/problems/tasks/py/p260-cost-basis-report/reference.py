def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def cost_basis_report(events: list[list]) -> dict:
    if not isinstance(events, list):
        raise ValueError("cost_basis_report expects a list of warehouse events")
    layers = []
    fifo_sold = 0
    pool_units = 0
    pool_cost = 0
    average_sold = 0

    for row in events:
        if not isinstance(row, list) or not row:
            raise ValueError("every event is a row naming buy or sell")
        kind = row[0]
        if kind not in ("buy", "sell"):
            raise ValueError(f"unknown event {kind!r}")
        if len(row) < 2 or not _whole(row[1]) or row[1] <= 0:
            raise ValueError("units must be a whole number above zero")
        count = row[1]
        if kind == "buy":
            if len(row) != 3:
                raise ValueError("a receipt is a kind, a unit count and a unit price")
            price = row[2]
            if not _whole(price) or price < 0:
                raise ValueError(
                    "a unit price must be a whole number of cents, not below zero"
                )
            layers.append([count, price])
            pool_units += count
            pool_cost += count * price
            continue
        if len(row) != 2:
            raise ValueError("a despatch is a kind and a unit count")
        if count > pool_units:
            raise ValueError("a despatch cannot exceed the stock on hand")
        wanted = count
        while wanted > 0:
            layer = layers[0]
            taken = min(wanted, layer[0])
            fifo_sold += taken * layer[1]
            layer[0] -= taken
            wanted -= taken
            if layer[0] == 0:
                layers.pop(0)
        charged = pool_cost * count // pool_units
        average_sold += charged
        pool_cost -= charged
        pool_units -= count

    fifo_value = sum(units * price for units, price in layers)
    return {
        "fifoSold": fifo_sold,
        "averageSold": average_sold,
        "unitsLeft": pool_units,
        "fifoValue": fifo_value,
        "averageValue": pool_cost,
    }
