def chunk_list(items: list, size: int) -> list[list]:
    """Split items into consecutive chunks of at most `size` elements."""
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    return [items[i:i + size] for i in range(0, len(items), size)]
