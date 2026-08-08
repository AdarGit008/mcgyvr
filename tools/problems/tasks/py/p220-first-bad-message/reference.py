KINDS = ("HELLO", "OFFER", "CHOOSE", "ACCEPT", "DATA", "BYE")

_STEPS = {
    (0, "client", "HELLO"): 1,
    (1, "server", "OFFER"): 2,
    (2, "client", "CHOOSE"): 3,
    (3, "server", "ACCEPT"): 4,
    (4, "client", "DATA"): 5,
    (4, "client", "BYE"): 6,
    (5, "server", "DATA"): 4,
    (6, "server", "BYE"): 7,
}


def first_bad_message(exchange: object) -> int:
    if not isinstance(exchange, list) or not exchange:
        raise ValueError("the exchange must be a non-empty list")
    state = 0
    for index, message in enumerate(exchange):
        if not isinstance(message, dict):
            raise ValueError("a message must be a mapping")
        side = message.get("from")
        kind = message.get("kind")
        if side not in ("client", "server"):
            raise ValueError("a message must come from the client or the server")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError("a message kind must be one of the six names")
        moved = _STEPS.get((state, side, kind))
        if moved is None:
            return index
        state = moved
    return -1 if state == 7 else len(exchange)
