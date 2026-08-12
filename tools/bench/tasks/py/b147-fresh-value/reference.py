def fresh_value(entry, now):
    if not isinstance(entry, dict):
        raise ValueError("entry must be a cache record")
    value, stored, ttl = entry.get("value"), entry.get("stored"), entry.get("ttl")
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    if not isinstance(stored, int) or stored < 0:
        raise ValueError("stored must be a non-negative integer")
    if not isinstance(ttl, int) or ttl < 1:
        raise ValueError("ttl must be a positive integer")
    if not isinstance(now, int) or now < stored:
        raise ValueError("now must be an integer no earlier than stored")
    if now >= stored + ttl:
        raise ValueError("record is no longer usable at now")
    return value
