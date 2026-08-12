def seal_code(code):
    if not isinstance(code, str) or code == "":
        raise ValueError("seal_code expects a non-empty string")
    glyphs = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    seal = 7
    for ch in code:
        worth = glyphs.find(ch)
        if worth < 0:
            raise ValueError("code holds a character outside digits and capitals")
        seal = (seal * 2 + worth) % 36
    return code + glyphs[seal]
