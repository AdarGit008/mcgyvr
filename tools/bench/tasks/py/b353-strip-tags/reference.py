def strip_tags(line: str) -> str:
    out = ""
    inside = False
    for ch in line:
        if ch == "<":
            inside = True
        elif ch == ">":
            inside = False
        elif not inside:
            out += ch
    return out
