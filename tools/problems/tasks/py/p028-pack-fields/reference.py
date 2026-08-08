def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def pack_fields(widths: list[int], values: list[int]) -> int:
    if not isinstance(widths, list) or not isinstance(values, list):
        raise ValueError("pack_fields expects two lists")
    if len(widths) != len(values):
        raise ValueError("widths and values must have the same length")
    if not widths:
        raise ValueError("at least one field is required")
    total_width = 0
    for width in widths:
        if not _is_int(width) or width < 1:
            raise ValueError("each width must be a positive integer")
        total_width += width
    if total_width > 30:
        raise ValueError("combined width must not exceed 30 bits")
    packed = 0
    for width, value in zip(widths, values):
        if not _is_int(value) or value < 0:
            raise ValueError("each value must be a non-negative integer")
        if value >= 2**width:
            raise ValueError("value does not fit in its field width")
        packed = packed * 2**width + value
    return packed
