def cipher_shift(text: str, step: int) -> str:
    first = ord("a")
    out = ""
    for ch in text:
        code = ord(ch)
        if first <= code < first + 26:
            out += chr(first + (code - first + step) % 26)
        else:
            out += ch
    return out
