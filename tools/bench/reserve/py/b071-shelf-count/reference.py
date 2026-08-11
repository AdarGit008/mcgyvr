def shelf_count(on_hand, moves):
    if isinstance(on_hand, bool) or not isinstance(on_hand, int) or on_hand < 0:
        raise ValueError("starting count must be a non-negative integer")
    ending = on_hand
    peak = on_hand
    for move in moves:
        if not isinstance(move, list) or len(move) != 2:
            raise ValueError("each move is a [kind, qty] pair")
        kind, qty = move
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise ValueError("qty must be a positive integer")
        if kind == "receive":
            ending += qty
            peak = max(peak, ending)
        elif kind == "issue":
            if qty > ending:
                raise ValueError("issue exceeds the count on the shelf")
            ending -= qty
        else:
            raise ValueError("unknown move kind: %s" % kind)
    return {"ending": ending, "peak": peak}
