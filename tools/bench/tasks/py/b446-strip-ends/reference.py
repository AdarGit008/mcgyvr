def strip_ends(text: str, mark: str) -> str:
    """The text with a character removed from both of its ends."""
    out = text
    while out.startswith(mark):
        out = out[1:]
    while out.endswith(mark):
        out = out[:-1]
    return out
