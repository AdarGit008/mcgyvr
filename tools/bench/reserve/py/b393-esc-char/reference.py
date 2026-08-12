def esc_char(text: str, mark: str) -> str:
    out = ""
    for ch in text:
        if ch == mark or ch == "^":
            out += "^"
        out += ch
    return out
