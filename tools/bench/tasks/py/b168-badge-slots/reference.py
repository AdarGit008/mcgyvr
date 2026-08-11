def badge_text(pattern, fields):
    if not isinstance(pattern, str):
        raise ValueError("badge_text expects a string pattern")
    out, i = "", 0
    while i < len(pattern):
        if pattern[i] == ">": raise ValueError("a closing bracket sits outside any slot")
        if pattern[i] != "<": out, i = out + pattern[i], i + 1; continue
        end = pattern.find(">", i + 1)
        if end < 0: raise ValueError("an opening bracket is never closed")
        name = pattern[i + 1 : end]
        if not (name.isascii() and name.isalpha() and name.islower()): raise ValueError("slot name must be lowercase letters")
        if name not in fields: raise ValueError("the fields mapping holds no such name")
        out, i = out + fields[name], end + 1
    return out
