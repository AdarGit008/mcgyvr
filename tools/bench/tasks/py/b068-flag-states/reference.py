def flag_states(mask, catalog):
    if isinstance(mask, bool) or not isinstance(mask, int) or mask < 0:
        raise ValueError("mask must be a non-negative integer")
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("catalog must name at least one flag")
    if mask >= 1 << len(catalog):
        raise ValueError("mask sets a bit beyond the catalog")
    states = {}
    for bit, name in enumerate(catalog):
        if not isinstance(name, str) or not name:
            raise ValueError("flag names must be non-empty strings")
        if name in states:
            raise ValueError("repeated flag name: " + name)
        states[name] = bool((mask >> bit) & 1)
    return states
