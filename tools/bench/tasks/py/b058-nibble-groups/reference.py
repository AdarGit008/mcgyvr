"""Render a value as fixed-width unsigned binary, nibble-grouped."""


def format_bits(value, width):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("value must be a non-negative integer")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or width % 4
        or width > 32
    ):
        raise ValueError("width must be a positive multiple of 4, at most 32")
    if value >= 1 << width:
        raise ValueError("value does not fit in the width")
    groups = []
    for start in range(width - 4, -1, -4):
        bits = range(start + 3, start - 1, -1)
        groups.append("".join("1" if value >> bit & 1 else "0" for bit in bits))
    return " ".join(groups)
