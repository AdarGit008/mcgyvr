LADDER = (("m", 1000), ("cm", 10), ("mm", 1))


def split_length(mm: int) -> str:
    if not isinstance(mm, int) or isinstance(mm, bool):
        raise ValueError("length must be a whole number of millimetres")
    if mm < 0:
        raise ValueError("length must not be negative")
    parts, rest = [], mm
    for unit, size in LADDER:
        count, rest = divmod(rest, size)
        if count > 0:
            parts.append(f"{count}{unit}")
    return " ".join(parts) if parts else "0mm"
