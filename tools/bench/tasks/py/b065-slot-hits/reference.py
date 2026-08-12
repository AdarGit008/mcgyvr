"""Count the hits a key stream scores on a direct-mapped cache."""


def slot_hits(keys: list, slots: int) -> int:
    if isinstance(slots, bool) or not isinstance(slots, int) or slots <= 0:
        raise ValueError("slot count must be a positive integer")
    held = [None] * slots
    hits = 0
    for key in keys:
        if isinstance(key, bool) or not isinstance(key, int):
            raise ValueError("keys must be integers")
        slot = key % slots
        if held[slot] == key:
            hits += 1
        else:
            held[slot] = key
    return hits
