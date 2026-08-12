def run_index(entries: list, value: str, nth: int) -> int:
    if nth <= 0:
        raise ValueError("nth must be positive")
    seen = 0
    for i, entry in enumerate(entries):
        if entry == value:
            seen += 1
            if seen == nth:
                return i
    return -1
