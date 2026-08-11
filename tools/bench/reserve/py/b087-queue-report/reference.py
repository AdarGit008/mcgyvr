def queue_report(orders: list) -> dict:
    if not isinstance(orders, list):
        raise ValueError("queue_report expects a list of orders")
    finish = 0
    waited = 0
    longest = 0
    busy = 0
    previous = 0
    for entry in orders:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("each order is a pair")
        placed, handover = entry
        if not isinstance(placed, int) or placed < 0:
            raise ValueError("placement minute must be a non-negative integer")
        if not isinstance(handover, int) or handover < 1:
            raise ValueError("hand-over time must be a positive integer")
        if placed < previous:
            raise ValueError("placement minutes must never decrease")
        previous = placed
        start = max(placed, finish)
        wait = start - placed
        waited += wait
        longest = max(longest, wait)
        finish = start + handover
        busy += handover
    return {"waited": waited, "longest": longest, "idle": finish - busy}
