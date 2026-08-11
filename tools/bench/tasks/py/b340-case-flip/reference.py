def swap_case(text: str) -> str:
    """Text with the case of every letter turned over."""
    lower = "abcdefghijklmnopqrstuvwxyz"
    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = ""
    for ch in text:
        if ch in lower:
            out += ch.upper()
        elif ch in upper:
            out += ch.lower()
        else:
            out += ch
    return out
