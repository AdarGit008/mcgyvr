def render_data_size(total: int) -> str:
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError("count must be a non-negative integer")
    ladder = [
        ("GiB", 1024 * 1024 * 1024),
        ("MiB", 1024 * 1024),
        ("KiB", 1024),
        ("B", 1),
    ]
    parts = []
    rest = total
    for suffix, size in ladder:
        count = rest // size
        if count > 0:
            parts.append(f"{count}{suffix}")
        rest -= count * size
    return "0B" if not parts else " ".join(parts)
