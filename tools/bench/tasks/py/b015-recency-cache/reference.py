def _check_key(key):
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty string")


def _touch(cache, key):
    if key in cache["keys"]:
        cache["keys"].remove(key)
    cache["keys"].append(key)


def new_cache(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    return {"limit": limit, "keys": [], "store": {}}


def cache_write(cache, key, value):
    _check_key(key)
    if key in cache["store"]:
        cache["store"][key] = value
        _touch(cache, key)
        return []
    spilled = []
    if len(cache["keys"]) == cache["limit"]:
        oldest = cache["keys"].pop(0)
        del cache["store"][oldest]
        spilled.append(oldest)
    cache["store"][key] = value
    cache["keys"].append(key)
    return spilled


def cache_read(cache, key):
    _check_key(key)
    if key not in cache["store"]:
        raise ValueError(f"key not held: {key}")
    _touch(cache, key)
    return cache["store"][key]
