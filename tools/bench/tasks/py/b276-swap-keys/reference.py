def swap_keys(names: dict) -> dict:
    swapped = {}
    for name in sorted(names):
        code = names[name]
        if code and code not in swapped:
            swapped[code] = name
    return swapped
