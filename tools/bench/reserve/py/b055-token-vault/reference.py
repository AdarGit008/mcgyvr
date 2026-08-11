def token_save(vault, name, value, now, ttl):
    if not isinstance(name, str) or not name:
        raise ValueError("token name must be a non-empty string")
    if not isinstance(now, int) or not isinstance(ttl, int) or ttl <= 0:
        raise ValueError("now must be an integer and ttl a positive integer")
    vault[name] = [value, now + ttl]


def token_fetch(vault, name, now):
    held = vault.get(name)
    if held is None:
        return None
    if now >= held[1]:
        del vault[name]
        return None
    return held[0]
