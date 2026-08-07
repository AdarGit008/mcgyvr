def reassemble_stream(total: int, fragments: list[list]) -> str:
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ValueError("total must be a non-negative integer")
    slots: list[str | None] = [None] * total
    for offset, text in fragments:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        if offset + len(text) > total:
            raise ValueError("fragment runs past the declared end")
        for k, ch in enumerate(text):
            existing = slots[offset + k]
            if existing is not None and existing != ch:
                raise ValueError(f"conflict at position {offset + k}")
            slots[offset + k] = ch
    if any(slot is None for slot in slots):
        raise ValueError("uncovered position")
    return "".join(slots)
