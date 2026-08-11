def share_out(amount: int, parts: int) -> list[int]:
    if parts < 1:
        raise ValueError("there must be at least one part")
    base = amount // parts
    over = amount % parts
    out = []
    for i in range(parts):
        if i < over:
            out.append(base + 1)
        else:
            out.append(base)
    return out
