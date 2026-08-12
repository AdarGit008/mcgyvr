def font_clamp(size: int, smallest: int, largest: int) -> int:
    if smallest > largest:
        raise ValueError("range is inverted")
    if size < smallest:
        return smallest
    return largest if size > largest else size
