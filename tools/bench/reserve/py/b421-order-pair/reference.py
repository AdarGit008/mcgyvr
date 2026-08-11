def low_of(pair: list) -> int:
    return pair[0] if pair[0] < pair[1] else pair[1]


def order_pairs(pairs: list) -> list:
    """The pairs in order by their smaller number."""
    return sorted(pairs, key=low_of)
