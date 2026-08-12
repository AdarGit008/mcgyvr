"""Render a packed sixteen-bit settings word as named fields."""


def describe_word(word: int, fields: list) -> str:
    if sum(width for _, width in fields) != 16:
        raise ValueError("field widths must cover all sixteen bits")
    parts = []
    offset = 16
    for name, width in fields:
        offset -= width
        value = (word >> offset) & ((1 << width) - 1)
        if width == 1:
            parts.append(name + "=" + ("on" if value == 1 else "off"))
        else:
            parts.append(name + "=" + str(value))
    return ",".join(parts)
