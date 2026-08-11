"""Fill orders from the stock lots whose use-by dates fall soonest."""


def reserve_lots(lots: list, orders: list) -> dict:
    stock = [{"id": lot_id, "use_by": use_by, "left": held} for lot_id, use_by, held in lots]
    stock.sort(key=lambda lot: (lot["use_by"], lot["id"]))
    picks = []
    short = []
    for order_id, wanted in orders:
        need = wanted
        for lot in stock:
            if need == 0:
                break
            take = min(lot["left"], need)
            if take > 0:
                lot["left"] -= take
                need -= take
                picks.append([order_id, lot["id"], take])
        if need > 0:
            short.append([order_id, need])
    return {"picks": picks, "short": short}
