def dupe_keys(ids: list) -> list:
    seen = set()
    repeated = []
    for key in ids:
        if key in seen and key not in repeated:
            repeated.append(key)
        seen.add(key)
    return repeated
