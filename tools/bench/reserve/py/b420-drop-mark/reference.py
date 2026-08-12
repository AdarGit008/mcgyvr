def drop_mark(text: str, mark: str) -> str:
    """The text with every occurrence of a marked character removed."""
    out = ""
    for ch in text:
        if ch != mark:
            out += ch
    return out
