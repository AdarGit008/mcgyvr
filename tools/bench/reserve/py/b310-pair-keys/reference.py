def pair_keys(names: list, codes: list) -> dict:
    paired = {}
    for i in range(min(len(names), len(codes))):
        paired[names[i]] = codes[i]
    return paired
