def draw_stock(shelf: dict, order: list) -> dict:
    for item, count in shelf.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("bad shelf count for " + str(item))
    if not isinstance(order, list):
        raise ValueError("draw_stock expects a list of order lines")
    left = dict(shelf)
    for item, count in order:
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("line count must be a positive integer")
        if item not in left or count > left[item]:
            raise ValueError("cannot pull " + str(count) + " of " + str(item))
        left[item] -= count
    return left
