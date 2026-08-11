def span_letters(span: str) -> str:
    if len(span) != 3 or span[1] != "-":
        return span
    start = ord(span[0])
    end = ord(span[2])
    if start > end:
        return span
    out = ""
    for code in range(start, end + 1):
        out += chr(code)
    return out
