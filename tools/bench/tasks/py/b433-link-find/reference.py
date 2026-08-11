def link_find(line: str, opens: str, closes: str) -> list:
    found = []
    inside = False
    current = ""
    for ch in line:
        if not inside and ch == opens:
            inside = True
            current = ""
        elif inside and ch == closes:
            inside = False
            found.append(current)
        elif inside:
            current += ch
    return found
