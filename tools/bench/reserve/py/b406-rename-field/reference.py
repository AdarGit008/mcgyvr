def rename_field(records: list, was: str, now: str) -> list:
    """Records with one field renamed."""
    out = []
    for record in records:
        copied = dict(record)
        if was in copied:
            copied[now] = copied[was]
            del copied[was]
        out.append(copied)
    return out
