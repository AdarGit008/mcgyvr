def in_quote(ch: str) -> bool:
    return ch == '"'


def quote_split(line: str) -> list:
    pieces = []
    current = ""
    quoted = False
    for ch in line:
        if in_quote(ch):
            quoted = not quoted
            current += ch
        elif ch == "," and not quoted:
            pieces.append(current)
            current = ""
        else:
            current += ch
    pieces.append(current)
    return pieces
