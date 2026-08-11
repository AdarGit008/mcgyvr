"""Render raw bytes as grouped lowercase hex for a debug line."""


def hex_groups(values, width):
    if not isinstance(values, list):
        raise ValueError("hex_groups expects a list of byte values")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("group width must be a positive integer")
    pairs = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError("every byte must be an integer from 0 to 255")
        pairs.append(format(value, "02x"))
    groups = []
    for start in range(0, len(pairs), width):
        groups.append("".join(pairs[start : start + width]))
    return " ".join(groups)
