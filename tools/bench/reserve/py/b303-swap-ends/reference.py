def swap_ends(items: list) -> list:
    """A list with its first and last entries exchanged."""
    if len(items) < 2:
        return items
    copied = list(items)
    copied[0], copied[-1] = copied[-1], copied[0]
    return copied
