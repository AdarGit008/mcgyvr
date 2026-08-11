def half_split(entries: list) -> list:
    cut = (len(entries) + 1) // 2
    return [entries[:cut], entries[cut:]]
