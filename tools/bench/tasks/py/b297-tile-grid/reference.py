def tiles_across(length: int, tile: int) -> int:
    return (length + tile - 1) // tile


def tiles_needed(width: int, height: int, tile: int, spare: int) -> int:
    plain = tiles_across(width, tile) * tiles_across(height, tile)
    total = plain * (100 + spare)
    return (total + 99) // 100
